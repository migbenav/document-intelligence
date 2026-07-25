"""Analysis API endpoints: initiate analysis, confirm type, retrieve knowledge model.

Provides:
- POST /{document_id}/analyze — starts analysis pipeline (Req 9.1, 9.2, 9.7)
- POST /{document_id}/confirm-type — confirms document type (Req 4.4, 4.5)
- GET /{document_id}/knowledge-model — retrieves completed KM (Req 9.4, 9.5, 9.6)
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.analysis.service import (
    AnalysisAlreadyExistsError,
    AnalysisService,
    DocumentNotFoundError,
    DocumentNotReadyError,
    InvalidDocumentTypeError,
    InvalidSessionStateError,
    VALID_DOCUMENT_TYPES,
)

router = APIRouter()


# --- Dependency injection helper ---


def _get_analysis_service() -> AnalysisService:
    """Dependency placeholder for the AnalysisService.

    Overridden by app factory dependency_overrides at startup
    with the fully constructed service instance.
    """
    raise NotImplementedError("AnalysisService dependency not configured")


# --- Request models ---


class ConfirmTypeRequest(BaseModel):
    """Request body for the confirm-type endpoint."""

    document_type: str


# --- Endpoints ---


@router.post(
    "/{document_id}/analyze",
    status_code=202,
    responses={
        404: {"description": "Document not found"},
        409: {"description": "Document not ready or analysis already exists"},
    },
)
async def analyze_document(
    document_id: str,
    analysis_service: AnalysisService = Depends(_get_analysis_service),
):
    """Initiate analysis for a document.

    Runs type inference and returns the session with a suggested type.
    Returns 202 on success with session details.
    Returns 404 if the document does not exist (Req 9.2).
    Returns 409 if the document is not in "ready" status (Req 9.1)
    or if analysis already exists (Req 9.7).
    """
    try:
        session = await analysis_service.start_analysis(document_id)
    except DocumentNotFoundError:
        return JSONResponse(
            status_code=404,
            content={
                "error": "not_found",
                "message": f"Document '{document_id}' not found",
            },
        )
    except DocumentNotReadyError:
        return JSONResponse(
            status_code=409,
            content={
                "error": "not_ready",
                "message": f"Document '{document_id}' is not ready for analysis. Ingestion must be complete.",
            },
        )
    except AnalysisAlreadyExistsError:
        return JSONResponse(
            status_code=409,
            content={
                "error": "analysis_exists",
                "message": f"Analysis already exists for document '{document_id}'.",
            },
        )

    return JSONResponse(
        status_code=202,
        content={
            "session_id": session.id,
            "document_id": session.document_id,
            "status": session.status,
            "suggested_type": session.suggested_type,
            "suggested_type_justification": session.suggested_type_justification,
        },
    )


@router.post(
    "/{document_id}/confirm-type",
    status_code=202,
    responses={
        400: {"description": "Invalid document type"},
        404: {"description": "Document/session not found"},
        409: {"description": "Session not in correct state"},
    },
)
async def confirm_document_type(
    document_id: str,
    body: ConfirmTypeRequest,
    analysis_service: AnalysisService = Depends(_get_analysis_service),
):
    """Confirm the document type and trigger extraction.

    Accepts a document_type from the valid set (prd, technical_spec,
    policy_process, generic). Returns 202 on success.
    Returns 400 with list of valid types on invalid value (Req 4.5).
    Returns 404 if document/session not found.
    Returns 409 if session is not in 'awaiting_confirmation' or already completed (Req 4.4).
    """
    try:
        session = await analysis_service.confirm_and_extract(
            document_id, body.document_type
        )
    except InvalidDocumentTypeError as e:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_document_type",
                "message": str(e),
                "valid_types": e.valid_types,
            },
        )
    except DocumentNotFoundError:
        return JSONResponse(
            status_code=404,
            content={
                "error": "not_found",
                "message": f"No analysis session found for document '{document_id}'.",
            },
        )
    except InvalidSessionStateError as e:
        return JSONResponse(
            status_code=409,
            content={
                "error": "invalid_session_state",
                "message": str(e),
            },
        )

    return JSONResponse(
        status_code=202,
        content={
            "session_id": session.id,
            "document_id": session.document_id,
            "status": session.status,
            "confirmed_type": session.confirmed_type,
        },
    )


@router.get(
    "/{document_id}/knowledge-model",
    status_code=200,
    responses={
        404: {"description": "Document not found"},
        409: {"description": "Analysis not yet completed"},
    },
)
async def get_knowledge_model(
    document_id: str,
    analysis_service: AnalysisService = Depends(_get_analysis_service),
):
    """Retrieve the Knowledge Model for a completed analysis.

    Returns 200 with the full Knowledge Model (elements, relationships,
    extraction_metadata) when analysis is complete (Req 9.4).
    Returns 404 if document/session not found (Req 9.6).
    Returns 409 if analysis is not yet completed (Req 9.5).
    """
    # First check if session exists
    session = await analysis_service.get_session(document_id)
    if session is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "not_found",
                "message": f"No analysis session found for document '{document_id}'.",
            },
        )

    # Check if analysis is completed
    if session.status != "completed":
        return JSONResponse(
            status_code=409,
            content={
                "error": "not_completed",
                "message": f"Analysis for document '{document_id}' is not yet completed. Current status: {session.status}.",
            },
        )

    # Retrieve the knowledge model
    km = await analysis_service.get_knowledge_model(document_id)
    if km is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "not_found",
                "message": f"Knowledge model not found for document '{document_id}'.",
            },
        )

    return JSONResponse(status_code=200, content=km)
