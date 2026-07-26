"""Document card retrieval and LLM retry endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.analysis.base_analysis.service import BaseAnalysisService, CardNotFoundError
from app.analysis.base_analysis.storage import BaseAnalysisStorage
from app.ingestion.storage import StorageService
from app.models.document_card import DocumentCard

router = APIRouter()


# --- Dependency injection helpers ---


def _get_base_analysis_service() -> BaseAnalysisService:
    """Dependency placeholder for the BaseAnalysisService.

    Overridden by app factory dependency_overrides at startup.
    """
    raise NotImplementedError("BaseAnalysisService dependency not configured")


def _get_base_analysis_storage() -> BaseAnalysisStorage:
    """Dependency placeholder for the BaseAnalysisStorage.

    Overridden by app factory dependency_overrides at startup.
    """
    raise NotImplementedError("BaseAnalysisStorage dependency not configured")


def _get_storage_service() -> StorageService:
    """Dependency placeholder for the StorageService (ingestion).

    Overridden by app factory dependency_overrides at startup.
    """
    raise NotImplementedError("StorageService dependency not configured")


def _validate_uuid(document_id: str) -> str | None:
    """Validate that document_id is a valid UUID string.

    Returns the normalized UUID string if valid, None otherwise.
    """
    try:
        return str(UUID(document_id))
    except (ValueError, AttributeError):
        return None


# --- Endpoints ---


@router.get(
    "/{document_id}/card",
    response_model=DocumentCard,
    responses={
        404: {"description": "Card or document not found"},
    },
)
async def get_document_card(
    document_id: str,
    storage: BaseAnalysisStorage = Depends(_get_base_analysis_storage),
    ingestion_storage: StorageService = Depends(_get_storage_service),
):
    """Retrieve the document card for a given document.

    Returns 200 with the DocumentCard if it exists.
    Returns 404 with error code "document_not_found" if the document doesn't exist.
    Returns 404 with error code "card_not_found" if the document exists but has no card.
    """
    # Validate UUID format
    normalized_id = _validate_uuid(document_id)
    if normalized_id is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "document_not_found",
                "message": f"Document '{document_id}' not found",
            },
        )

    # Check if document exists
    doc_status = await ingestion_storage.get_status(normalized_id)
    if doc_status is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "document_not_found",
                "message": f"Document '{normalized_id}' not found",
            },
        )

    # Check if card exists
    card = await storage.get_card(normalized_id)
    if card is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "card_not_found",
                "message": f"Card for document '{normalized_id}' is not yet available",
            },
        )

    return card


@router.post(
    "/{document_id}/card/retry-llm",
    response_model=DocumentCard,
    responses={
        404: {"description": "Card not found"},
        409: {"description": "Card already complete"},
    },
)
async def retry_llm(
    document_id: str,
    analysis_service: BaseAnalysisService = Depends(_get_base_analysis_service),
    storage: BaseAnalysisStorage = Depends(_get_base_analysis_storage),
    ingestion_storage: StorageService = Depends(_get_storage_service),
):
    """Retry only the LLM phase for a partial or failed card.

    Returns 200 with the updated DocumentCard on success.
    Returns 404 with error code "card_not_found" if no card exists.
    Returns 409 with error code "card_already_complete" if card status is "completed".
    """
    # Validate UUID format
    normalized_id = _validate_uuid(document_id)
    if normalized_id is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "card_not_found",
                "message": f"No card exists for document '{document_id}'",
            },
        )

    # Check if card exists and its status
    card = await storage.get_card(normalized_id)
    if card is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "card_not_found",
                "message": f"No card exists for document '{normalized_id}'",
            },
        )

    # If card is already completed, return 409
    if card.status == "completed":
        return JSONResponse(
            status_code=409,
            content={
                "error": "card_already_complete",
                "message": f"Card for document '{normalized_id}' already has status 'completed' and does not need LLM retry",
            },
        )

    # Retrieve the IR for context
    ir = await ingestion_storage.get_ir(normalized_id)
    if ir is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "card_not_found",
                "message": f"Cannot retry LLM: intermediate representation not available for document '{normalized_id}'",
            },
        )

    # Execute LLM retry
    updated_card = await analysis_service.retry_llm(normalized_id, ir)
    return updated_card
