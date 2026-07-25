"""Quality Analysis API endpoints: trigger and retrieve quality analysis.

Provides:
- POST /{document_id}/quality-analysis — triggers quality analysis pipeline (Req 5.2)
- GET /{document_id}/quality-analysis — retrieves quality analysis results (Req 5.1, 5.3–5.8)

Requirements covered: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8
"""

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import JSONResponse

from app.analysis.quality.service import (
    AnalysisInProgressError,
    KMNotCompletedError,
    QualityAnalysisService,
)
from app.analysis.service import AnalysisStorageService

router = APIRouter()


# --- Dependency injection helpers ---


def _get_quality_analysis_service() -> QualityAnalysisService:
    """Dependency placeholder for the QualityAnalysisService.

    Overridden by app factory dependency_overrides at startup
    with the fully constructed service instance.
    """
    raise NotImplementedError("QualityAnalysisService dependency not configured")


def _get_analysis_storage_service() -> AnalysisStorageService:
    """Dependency placeholder for AnalysisStorageService.

    Overridden by app factory dependency_overrides at startup.
    """
    raise NotImplementedError("AnalysisStorageService dependency not configured")


# --- Background task runner ---


async def _run_quality_analysis_background(
    service: QualityAnalysisService, document_id: str
) -> None:
    """Run quality analysis as a background task.

    Exceptions are handled internally by the service (marks as failed).
    """
    try:
        await service.run_analysis(document_id)
    except Exception:
        # Service already marks the session as failed on error.
        pass


# --- Endpoints ---


@router.post(
    "/{document_id}/quality-analysis",
    status_code=202,
    responses={
        404: {"description": "Document not found"},
        409: {"description": "KM not completed or analysis in progress"},
    },
)
async def trigger_quality_analysis(
    document_id: str,
    background_tasks: BackgroundTasks,
    quality_service: QualityAnalysisService = Depends(_get_quality_analysis_service),
    storage: AnalysisStorageService = Depends(_get_analysis_storage_service),
):
    """Trigger quality analysis for a document.

    Validates prerequisites (document exists, KM completed, no analysis running)
    and starts the pipeline as a background task. Returns 202 immediately.

    Returns 404 if document not found.
    Returns 409 if KM not completed or analysis already in progress.
    """
    # Check document exists
    doc = storage.get_document(document_id)
    if doc is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "not_found",
                "message": f"Document '{document_id}' not found.",
            },
        )

    # Check analysis session exists and KM is completed
    session = storage.get_session_by_document(document_id)
    if session is None or session.get("status") != "completed":
        current_status = session.get("status") if session else "not_found"
        return JSONResponse(
            status_code=409,
            content={
                "error": "km_not_completed",
                "message": (
                    f"Quality analysis requires a completed Knowledge Model. "
                    f"Current analysis status: {current_status}."
                ),
            },
        )

    # Check no analysis already in progress
    if session.get("quality_status") == "analyzing":
        return JSONResponse(
            status_code=409,
            content={
                "error": "analysis_in_progress",
                "message": (
                    "Quality analysis is already running for this document. "
                    "Wait for it to complete or fail before re-triggering."
                ),
            },
        )

    # Also check phase-specific analyzing statuses
    quality_status = session.get("quality_status")
    if quality_status is not None and (
        quality_status.startswith("analyzing_") or quality_status == "generating_suggestions"
    ):
        return JSONResponse(
            status_code=409,
            content={
                "error": "analysis_in_progress",
                "message": (
                    "Quality analysis is already running for this document. "
                    "Wait for it to complete or fail before re-triggering."
                ),
            },
        )

    # Trigger analysis in background
    background_tasks.add_task(
        _run_quality_analysis_background, quality_service, document_id
    )

    return JSONResponse(
        status_code=202,
        content={
            "document_id": document_id,
            "status": "analyzing",
        },
    )


@router.get(
    "/{document_id}/quality-analysis",
    status_code=200,
    responses={
        202: {"description": "Analysis in progress"},
        404: {"description": "Document not found or analysis not triggered"},
        409: {"description": "KM not completed"},
        500: {"description": "Analysis failed"},
    },
)
async def get_quality_analysis(
    document_id: str,
    quality_service: QualityAnalysisService = Depends(_get_quality_analysis_service),
    storage: AnalysisStorageService = Depends(_get_analysis_storage_service),
):
    """Retrieve quality analysis results for a document.

    Returns the appropriate response based on the current quality analysis state:
    - 200: Analysis completed, returns full results with metadata (Req 5.1, 5.7, 5.8)
    - 202: Analysis in progress, returns current phase (Req 5.3)
    - 404: Document not found or analysis not triggered (Req 5.5)
    - 409: KM not completed (Req 5.4)
    - 500: Analysis failed with error details (Req 5.6)
    """
    # Check document exists
    doc = storage.get_document(document_id)
    if doc is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "not_found",
                "message": f"Document '{document_id}' not found.",
            },
        )

    # Check analysis session exists
    session = storage.get_session_by_document(document_id)
    if session is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "not_found",
                "message": f"No analysis session found for document '{document_id}'.",
            },
        )

    # Check KM is completed
    if session.get("status") != "completed":
        return JSONResponse(
            status_code=409,
            content={
                "error": "km_not_completed",
                "message": (
                    f"Quality analysis requires a completed Knowledge Model. "
                    f"Current analysis status: {session.get('status')}."
                ),
            },
        )

    # Check quality analysis state
    quality_status = session.get("quality_status")

    # Not triggered yet
    if quality_status is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "not_found",
                "message": (
                    f"Quality analysis has not been triggered for document '{document_id}'. "
                    f"Use POST to trigger analysis first."
                ),
            },
        )

    # In progress (any analyzing phase)
    if quality_status in (
        "analyzing",
        "analyzing_contradictions",
        "analyzing_ambiguities",
        "analyzing_completeness",
        "generating_suggestions",
    ):
        return JSONResponse(
            status_code=202,
            content={
                "document_id": document_id,
                "status": quality_status,
            },
        )

    # Failed
    if quality_status == "failed":
        error_message = session.get("quality_error_message", "Unknown error")
        # Try to extract phase from stored quality_analysis
        error_phase = None
        quality_analysis = session.get("quality_analysis")
        if quality_analysis:
            if isinstance(quality_analysis, dict):
                error_phase = quality_analysis.get("error_phase")

        content = {
            "error": "analysis_failed",
            "message": f"Quality analysis failed: {error_message}",
        }
        if error_phase:
            content["phase"] = error_phase

        return JSONResponse(
            status_code=500,
            content=content,
        )

    # Completed — return full results (Req 5.1, 5.7, 5.8)
    if quality_status == "completed":
        result = await quality_service.get_results(document_id)
        if result is None:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "analysis_failed",
                    "message": "Quality analysis marked as completed but results not found.",
                },
            )

        return JSONResponse(
            status_code=200,
            content=result.model_dump(mode="json"),
        )

    # Fallback for unexpected status values
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": f"Unexpected quality analysis status: {quality_status}",
        },
    )
