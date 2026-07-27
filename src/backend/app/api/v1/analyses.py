"""On-demand analysis endpoints: trigger, status summary, and result retrieval.

Provides:
- POST /{document_id}/analyses/{analysis_type} — trigger analysis or return cached (Req 7.1-6)
- GET /{document_id}/analyses — status summary for all types (Req 7.7)
- GET /{document_id}/analyses/{analysis_type} — retrieve stored result (Req 7.8)

Requirements covered: Req 7 (criteria 1-9)
"""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.analysis.on_demand.models import AnalysisRecord, AnalysisStatus, AnalysisType
from app.analysis.on_demand.service import (
    DocumentIRNotAvailableError,
    OnDemandAnalysisService,
)
from app.ingestion.storage import StorageService
from app.middleware.preferences import RequestPreferences, get_request_preferences

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Dependency injection helpers ---


def _get_on_demand_analysis_service() -> OnDemandAnalysisService:
    """Dependency placeholder for the OnDemandAnalysisService.

    Overridden by app factory dependency_overrides at startup
    with the fully constructed service instance.
    """
    raise NotImplementedError("OnDemandAnalysisService dependency not configured")


def _get_storage_service() -> StorageService:
    """Dependency placeholder for the StorageService (ingestion).

    Overridden by app factory dependency_overrides at startup.
    """
    raise NotImplementedError("StorageService dependency not configured")


# --- Endpoints ---


@router.post(
    "/{document_id}/analyses/{analysis_type}",
    status_code=200,
    responses={
        404: {"description": "Document not found"},
        409: {"description": "Document IR not available"},
        502: {"description": "LLM call failed"},
    },
)
async def trigger_analysis(
    document_id: str,
    analysis_type: AnalysisType,
    service: OnDemandAnalysisService = Depends(_get_on_demand_analysis_service),
    ingestion_storage: StorageService = Depends(_get_storage_service),
    prefs: RequestPreferences = Depends(get_request_preferences),
):
    """Trigger an on-demand analysis or return cached result.

    Validates the analysis_type against the AnalysisType enum (FastAPI handles
    422 automatically for invalid enum values). Calls the service to execute the
    analysis (or return a cached result if idempotent).

    Returns 200 with the full AnalysisRecord on success.
    Returns 404 if the document does not exist.
    Returns 409 if the document IR is not available.
    Returns 502 if the LLM call fails.
    """
    # Check if document exists
    doc_status = await ingestion_storage.get_status(document_id)
    if doc_status is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "document_not_found",
                "message": f"Document '{document_id}' not found",
            },
        )

    # Build preferences dict for the service
    preferences = {
        "language": prefs.language,
        "model_override": prefs.model_override,
        "auto_fallback": prefs.auto_fallback,
    }

    try:
        record: AnalysisRecord = await service.execute(
            document_id=document_id,
            analysis_type=analysis_type,
            preferences=preferences,
        )
    except DocumentIRNotAvailableError:
        return JSONResponse(
            status_code=409,
            content={
                "error": "document_not_ready",
                "message": f"Document '{document_id}' IR is not available. "
                "Document may not be ingested or processing is incomplete.",
            },
        )
    except Exception as exc:
        # LLM failures, timeouts, analyzer errors → 502
        logger.error(
            "Analysis failed for document '%s' type '%s': %s",
            document_id,
            analysis_type.value,
            str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=502,
            content={
                "error": "analysis_failed",
                "message": f"Analysis failed: {str(exc)}",
            },
        )

    return JSONResponse(
        status_code=200,
        content=record.model_dump(mode="json"),
    )


@router.get(
    "/{document_id}/analyses",
    status_code=200,
    responses={
        404: {"description": "Document not found"},
    },
)
async def get_all_statuses(
    document_id: str,
    service: OnDemandAnalysisService = Depends(_get_on_demand_analysis_service),
    ingestion_storage: StorageService = Depends(_get_storage_service),
):
    """Get the status summary for all analysis types of a document.

    Returns 200 with a dict mapping each analysis type to its status and updated_at.
    Returns 404 if the document does not exist.
    """
    # Check if document exists
    doc_status = await ingestion_storage.get_status(document_id)
    if doc_status is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "document_not_found",
                "message": f"Document '{document_id}' not found",
            },
        )

    statuses = await service.get_all_statuses(document_id)
    return JSONResponse(status_code=200, content=statuses)


@router.get(
    "/{document_id}/analyses/{analysis_type}",
    status_code=200,
    responses={
        404: {"description": "Document not found"},
    },
)
async def get_analysis_result(
    document_id: str,
    analysis_type: AnalysisType,
    service: OnDemandAnalysisService = Depends(_get_on_demand_analysis_service),
    ingestion_storage: StorageService = Depends(_get_storage_service),
):
    """Retrieve the stored result for a specific analysis type.

    Returns 200 with the full AnalysisRecord if the analysis has been executed.
    Returns 200 with status "not_started" if no result exists.
    Returns 404 if the document does not exist.
    """
    # Check if document exists
    doc_status = await ingestion_storage.get_status(document_id)
    if doc_status is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "document_not_found",
                "message": f"Document '{document_id}' not found",
            },
        )

    record = await service.get_result(document_id, analysis_type)

    if record is None:
        return JSONResponse(
            status_code=200,
            content={
                "analysis_type": analysis_type.value,
                "status": AnalysisStatus.NOT_STARTED.value,
                "result": None,
            },
        )

    return JSONResponse(
        status_code=200,
        content=record.model_dump(mode="json"),
    )
