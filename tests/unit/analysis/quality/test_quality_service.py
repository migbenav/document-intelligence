"""Unit tests for the QualityAnalysisService orchestrator.

Tests cover:
- Full happy path (pipeline completes successfully)
- KM not completed rejects analysis
- Timeout triggers failure state
- LLM failure preserves structural contradictions
- Re-trigger overwrites previous results
- Phase updates written to DB

Requirements validated: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 8.1, 8.2, 8.3, 8.5, 8.6, 9.3, 9.4
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.analysis.quality.ambiguity_detector import AmbiguityDetector
from app.analysis.quality.completeness_evaluator import CompletenessEvaluator
from app.analysis.quality.contradiction_detector import ContradictionDetector
from app.analysis.quality.finding_verifier import FindingVerifier
from app.analysis.quality.service import (
    AnalysisInProgressError,
    KMNotCompletedError,
    QualityAnalysisService,
)
from app.analysis.quality.suggestion_generator import SuggestionGenerator
from app.analysis.service import AnalysisStorageService
from app.models.quality_analysis import (
    FindingSourceRef,
    Inconsistency,
    MissingElement,
    Suggestion,
)


# --- Fixtures ---

SAMPLE_KM_DICT = {
    "document_id": "doc-001",
    "document_type": "prd",
    "elements": [
        {
            "id": "elem-001",
            "type": "proposito",
            "name": "Document Purpose",
            "content": "This defines the API.",
            "source_ref": {
                "document_id": "doc-001",
                "chunk_id": "chunk-001",
                "section": "## Purpose",
                "evidence": "This defines the API.",
            },
            "relations": [
                {
                    "target_id": "elem-002",
                    "type": "contradicts",
                    "description": "Conflicting info",
                }
            ],
            "verified": True,
        },
        {
            "id": "elem-002",
            "type": "restriccion",
            "name": "Constraint",
            "content": "Max 200ms response.",
            "source_ref": {
                "document_id": "doc-001",
                "chunk_id": "chunk-002",
                "section": "## Constraints",
                "evidence": "Max 200ms response.",
            },
            "relations": [],
            "verified": False,
        },
    ],
    "extraction_metadata": {
        "prompt_version": "extraction-v1",
        "model_id": "gemini/gemini-2.5-flash-preview-05-20",
        "temperature": 0.1,
        "element_count": 2,
        "relationship_count": 1,
        "verification_rate": 0.5,
        "extracted_at": "2025-01-01T00:00:00Z",
    },
}


SAMPLE_DOC_ROW = {
    "document_id": "doc-001",
    "original_filename": "test.md",
    "format": "markdown",
    "size_bytes": 1024,
    "language": "en",
    "upload_timestamp": "2025-01-01T00:00:00+00:00",
    "status": "ready",
    "warnings": [],
}

SAMPLE_CHUNKS_DATA = [
    {
        "chunk_id": "chunk-001",
        "text": "This defines the API.",
        "structural_context": {"section": "## Purpose"},
        "order": 0,
    },
    {
        "chunk_id": "chunk-002",
        "text": "Max 200ms response.",
        "structural_context": {"section": "## Constraints"},
        "order": 1,
    },
]


def _make_completed_session(quality_status=None, quality_analysis=None):
    """Create a mock session row with status 'completed'."""
    return {
        "id": "session-001",
        "document_id": "doc-001",
        "status": "completed",
        "confirmed_type": "prd",
        "knowledge_model": SAMPLE_KM_DICT,
        "quality_status": quality_status,
        "quality_analysis": quality_analysis,
        "quality_started_at": None,
        "quality_completed_at": None,
        "quality_error_message": None,
    }


@pytest.fixture
def mock_storage():
    """Create a mock AnalysisStorageService."""
    storage = MagicMock(spec=AnalysisStorageService)
    storage.get_session_by_document.return_value = _make_completed_session()
    storage.get_document.return_value = SAMPLE_DOC_ROW
    storage.get_ir.return_value = SAMPLE_CHUNKS_DATA
    storage.update_session.return_value = _make_completed_session()
    return storage


@pytest.fixture
def mock_contradiction_detector():
    """Create a mock ContradictionDetector."""
    detector = MagicMock(spec=ContradictionDetector)
    detector.detect = AsyncMock(return_value=[])
    detector._llm_client = MagicMock()
    detector._llm_client.primary_model = "gemini/gemini-2.5-flash-preview-05-20"
    detector._collect_structural_contradictions = MagicMock(return_value=[])
    return detector


@pytest.fixture
def mock_ambiguity_detector():
    """Create a mock AmbiguityDetector."""
    detector = MagicMock(spec=AmbiguityDetector)
    detector.detect = AsyncMock(return_value=[])
    return detector


@pytest.fixture
def mock_completeness_evaluator():
    """Create a mock CompletenessEvaluator."""
    evaluator = MagicMock(spec=CompletenessEvaluator)
    evaluator.evaluate = AsyncMock(return_value=[])
    return evaluator


@pytest.fixture
def mock_suggestion_generator():
    """Create a mock SuggestionGenerator."""
    generator = MagicMock(spec=SuggestionGenerator)
    generator.generate = AsyncMock(return_value=[])
    return generator


@pytest.fixture
def mock_finding_verifier():
    """Create a mock FindingVerifier."""
    verifier = MagicMock(spec=FindingVerifier)
    verifier.verify_all.return_value = ([], [])
    return verifier


@pytest.fixture
def service(
    mock_contradiction_detector,
    mock_ambiguity_detector,
    mock_completeness_evaluator,
    mock_suggestion_generator,
    mock_finding_verifier,
    mock_storage,
):
    """Create a QualityAnalysisService with all mocked dependencies."""
    return QualityAnalysisService(
        contradiction_detector=mock_contradiction_detector,
        ambiguity_detector=mock_ambiguity_detector,
        completeness_evaluator=mock_completeness_evaluator,
        suggestion_generator=mock_suggestion_generator,
        finding_verifier=mock_finding_verifier,
        storage=mock_storage,
    )


# --- Test: Full Happy Path ---


class TestFullHappyPath:
    """Test that the pipeline completes successfully with all steps."""

    @pytest.mark.asyncio
    async def test_run_analysis_returns_completed_result(self, service, mock_storage):
        """Full pipeline returns QualityAnalysisResult with status completed."""
        result = await service.run_analysis("doc-001")

        assert result.document_id == "doc-001"
        assert result.status == "completed"
        assert result.metadata is not None
        assert result.metadata.document_type == "prd"
        assert result.metadata.temperature == 0.1
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_run_analysis_persists_results(self, service, mock_storage):
        """Pipeline persists results to storage on success."""
        await service.run_analysis("doc-001")

        # Final update should set quality_status = "completed"
        update_calls = mock_storage.update_session.call_args_list
        final_call_kwargs = update_calls[-1].kwargs
        assert final_call_kwargs["quality_status"] == "completed"
        assert final_call_kwargs["quality_analysis"] is not None
        assert final_call_kwargs["quality_completed_at"] is not None


    @pytest.mark.asyncio
    async def test_run_analysis_includes_metadata(self, service, mock_storage):
        """Pipeline records prompt versions, model_id, temperature (Req 9.3)."""
        result = await service.run_analysis("doc-001")

        assert result.metadata is not None
        assert "contradiction_detection" in result.metadata.prompt_versions
        assert "ambiguity_detection" in result.metadata.prompt_versions
        assert "completeness_evaluation" in result.metadata.prompt_versions
        assert "suggestion_generation" in result.metadata.prompt_versions
        assert result.metadata.model_id == "gemini/gemini-2.5-flash-preview-05-20"
        assert result.metadata.temperature == 0.1
        assert result.metadata.started_at is not None
        assert result.metadata.completed_at is not None

    @pytest.mark.asyncio
    async def test_run_analysis_counts_findings(
        self,
        service,
        mock_storage,
        mock_contradiction_detector,
        mock_ambiguity_detector,
        mock_completeness_evaluator,
        mock_suggestion_generator,
        mock_finding_verifier,
    ):
        """Finding counts in metadata are accurate."""
        contradictions = [
            Inconsistency(
                id="c-001",
                type="contradiction",
                description="Test",
                severity="high",
                affected_element_ids=["e1", "e2"],
                source_refs=[
                    FindingSourceRef(
                        document_id="doc-001",
                        chunk_id="chunk-001",
                        evidence="ev1",
                    ),
                    FindingSourceRef(
                        document_id="doc-001",
                        chunk_id="chunk-002",
                        evidence="ev2",
                    ),
                ],
                from_explicit_relationship=True,
            )
        ]
        ambiguities = [
            Inconsistency(
                id="a-001",
                type="ambiguity",
                description="Ambig test",
                severity="medium",
                affected_element_ids=["e1"],
                source_refs=[
                    FindingSourceRef(
                        document_id="doc-001",
                        chunk_id="chunk-001",
                        evidence="ev",
                    )
                ],
            )
        ]
        mock_contradiction_detector.detect.return_value = contradictions
        mock_ambiguity_detector.detect.return_value = ambiguities
        mock_finding_verifier.verify_all.return_value = (
            contradictions + ambiguities,
            [],
        )

        result = await service.run_analysis("doc-001")

        assert result.metadata.finding_counts["contradictions"] == 1
        assert result.metadata.finding_counts["ambiguities"] == 1
        assert result.metadata.finding_counts["missing_elements"] == 0
        assert result.metadata.finding_counts["suggestions"] == 0


# --- Test: KM Not Completed Rejects ---


class TestKMNotCompletedRejects:
    """Test that quality analysis is rejected when KM is not completed (Req 8.1)."""

    @pytest.mark.asyncio
    async def test_session_not_found_raises(self, service, mock_storage):
        """No session found raises KMNotCompletedError."""
        mock_storage.get_session_by_document.return_value = None

        with pytest.raises(KMNotCompletedError):
            await service.run_analysis("doc-001")

    @pytest.mark.asyncio
    async def test_session_not_completed_raises(self, service, mock_storage):
        """Session with status != 'completed' raises KMNotCompletedError."""
        mock_storage.get_session_by_document.return_value = {
            "id": "session-001",
            "document_id": "doc-001",
            "status": "extracting",
            "quality_status": None,
        }

        with pytest.raises(KMNotCompletedError, match="extracting"):
            await service.run_analysis("doc-001")

    @pytest.mark.asyncio
    async def test_km_not_completed_does_not_modify_session(
        self, service, mock_storage
    ):
        """Rejected analysis does not create or modify quality records."""
        mock_storage.get_session_by_document.return_value = {
            "id": "session-001",
            "document_id": "doc-001",
            "status": "inferring_type",
            "quality_status": None,
        }

        with pytest.raises(KMNotCompletedError):
            await service.run_analysis("doc-001")

        mock_storage.update_session.assert_not_called()


# --- Test: Analysis In Progress Rejects ---


class TestAnalysisInProgressRejects:
    """Test that re-triggering while analyzing raises error."""

    @pytest.mark.asyncio
    async def test_analyzing_status_raises(self, service, mock_storage):
        """quality_status='analyzing' raises AnalysisInProgressError."""
        mock_storage.get_session_by_document.return_value = (
            _make_completed_session(quality_status="analyzing")
        )

        with pytest.raises(AnalysisInProgressError):
            await service.run_analysis("doc-001")


# --- Test: Timeout Triggers Failure ---


class TestTimeoutTriggersFailure:
    """Test that pipeline timeout marks analysis as failed (Req 6.7)."""

    @pytest.mark.asyncio
    async def test_timeout_raises_and_marks_failed(
        self, service, mock_storage, mock_contradiction_detector
    ):
        """Pipeline timeout sets quality_status='failed' with timeout message."""

        async def slow_detect(*args, **kwargs):
            await asyncio.sleep(200)
            return []

        mock_contradiction_detector.detect = slow_detect

        with patch(
            "app.analysis.quality.service.PIPELINE_TIMEOUT_SECONDS", 0.01
        ):
            with pytest.raises(asyncio.TimeoutError):
                await service.run_analysis("doc-001")

        # Verify that the session was marked as failed
        update_calls = mock_storage.update_session.call_args_list
        # Find the failure update call
        failure_calls = [
            c for c in update_calls if c.kwargs.get("quality_status") == "failed"
        ]
        assert len(failure_calls) >= 1
        failure_kwargs = failure_calls[-1].kwargs
        assert "timed out" in failure_kwargs.get("quality_error_message", "")


# --- Test: LLM Failure Preserves Structural Contradictions ---


class TestLLMFailurePreservesStructural:
    """Test that LLM failure preserves explicit contradictions (Req 6.4)."""

    @pytest.mark.asyncio
    async def test_ambiguity_failure_preserves_contradictions(
        self,
        service,
        mock_storage,
        mock_contradiction_detector,
        mock_ambiguity_detector,
    ):
        """Ambiguity detection failure preserves structural contradictions."""
        structural = Inconsistency(
            id="contra-struct-001",
            type="contradiction",
            description="Conflicting values",
            severity="high",
            affected_element_ids=["elem-001", "elem-002"],
            source_refs=[
                FindingSourceRef(
                    document_id="doc-001",
                    chunk_id="chunk-001",
                    evidence="200ms",
                ),
                FindingSourceRef(
                    document_id="doc-001",
                    chunk_id="chunk-002",
                    evidence="500ms",
                ),
            ],
            from_explicit_relationship=True,
        )
        mock_contradiction_detector._collect_structural_contradictions.return_value = [
            structural
        ]
        mock_ambiguity_detector.detect.side_effect = RuntimeError("LLM failed")

        with pytest.raises(RuntimeError):
            await service.run_analysis("doc-001")

        # Verify failed state persisted with explicit contradictions
        update_calls = mock_storage.update_session.call_args_list
        failure_calls = [
            c for c in update_calls if c.kwargs.get("quality_status") == "failed"
        ]
        assert len(failure_calls) >= 1
        failed_result = failure_calls[-1].kwargs.get("quality_analysis")
        assert failed_result is not None
        assert len(failed_result["inconsistencies"]) == 1
        assert (
            failed_result["inconsistencies"][0]["from_explicit_relationship"] is True
        )


# --- Test: Re-trigger Overwrites Previous Results ---


class TestRetriggerOverwritesPrevious:
    """Test that re-triggering quality analysis overwrites previous results (Req 6.6)."""

    @pytest.mark.asyncio
    async def test_retrigger_clears_previous_results(self, service, mock_storage):
        """Re-triggering resets quality_status and clears previous analysis."""
        # Session has previous completed analysis
        mock_storage.get_session_by_document.return_value = _make_completed_session(
            quality_status="completed",
            quality_analysis={"status": "completed", "inconsistencies": []},
        )

        await service.run_analysis("doc-001")

        # First update_session call should reset the quality state
        first_update = mock_storage.update_session.call_args_list[0]
        assert first_update.kwargs["quality_status"] == "analyzing"
        assert first_update.kwargs["quality_analysis"] is None

    @pytest.mark.asyncio
    async def test_retrigger_after_failure_works(self, service, mock_storage):
        """Re-triggering after a failed analysis proceeds normally."""
        mock_storage.get_session_by_document.return_value = _make_completed_session(
            quality_status="failed",
            quality_analysis=None,
        )

        result = await service.run_analysis("doc-001")

        assert result.status == "completed"


# --- Test: Phase Updates Written to DB ---


class TestPhaseUpdatesWrittenToDB:
    """Test that pipeline phase transitions are written to the DB (Req 6.2)."""

    @pytest.mark.asyncio
    async def test_all_phases_updated(self, service, mock_storage):
        """All pipeline phase transitions are recorded in the DB."""
        await service.run_analysis("doc-001")

        update_calls = mock_storage.update_session.call_args_list
        statuses = [c.kwargs.get("quality_status") for c in update_calls]

        # Expected phase progression
        assert "analyzing" in statuses
        assert "analyzing_contradictions" in statuses
        assert "analyzing_ambiguities" in statuses
        assert "analyzing_completeness" in statuses
        assert "generating_suggestions" in statuses
        assert "completed" in statuses


# --- Test: get_results ---


class TestGetResults:
    """Test the get_results method for idempotent retrieval (Req 5.8)."""

    @pytest.mark.asyncio
    async def test_get_results_returns_none_when_no_session(
        self, service, mock_storage
    ):
        """Returns None when no session exists."""
        mock_storage.get_session_by_document.return_value = None

        result = await service.get_results("doc-001")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_results_returns_none_when_no_analysis(
        self, service, mock_storage
    ):
        """Returns None when session exists but no quality_analysis."""
        mock_storage.get_session_by_document.return_value = _make_completed_session(
            quality_analysis=None
        )

        result = await service.get_results("doc-001")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_results_returns_result_when_completed(
        self, service, mock_storage
    ):
        """Returns QualityAnalysisResult when analysis is completed."""
        completed_result = {
            "document_id": "doc-001",
            "status": "completed",
            "inconsistencies": [],
            "missing_elements": [],
            "suggestions": [],
            "metadata": {
                "prompt_versions": {
                    "contradiction_detection": "contradiction-v1",
                    "ambiguity_detection": "ambiguity-v1",
                    "completeness_evaluation": "completeness-v1",
                    "suggestion_generation": "suggestion-v1",
                },
                "model_id": "gemini/gemini-2.5-flash",
                "temperature": 0.1,
                "document_type": "prd",
                "started_at": "2025-01-01T00:00:00Z",
                "completed_at": "2025-01-01T00:01:00Z",
                "finding_counts": {
                    "contradictions": 0,
                    "ambiguities": 0,
                    "missing_elements": 0,
                    "suggestions": 0,
                },
            },
        }
        mock_storage.get_session_by_document.return_value = _make_completed_session(
            quality_status="completed",
            quality_analysis=completed_result,
        )

        result = await service.get_results("doc-001")

        assert result is not None
        assert result.document_id == "doc-001"
        assert result.status == "completed"
        assert result.metadata is not None
