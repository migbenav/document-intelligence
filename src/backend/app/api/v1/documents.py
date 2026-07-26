"""Document upload, status, and IR retrieval endpoints."""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile
from fastapi.responses import JSONResponse

from app.analysis.base_analysis.service import BaseAnalysisService
from app.ingestion.service import IngestionService
from app.ingestion.storage import StorageService
from app.models.document import DocumentStatus, IntermediateRepresentation

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Dependency injection helpers ---


def _get_ingestion_service() -> IngestionService:
    """Dependency placeholder for the IngestionService.

    Overridden by app factory dependency_overrides or replaced
    at startup with the real configured instance.
    """
    raise NotImplementedError("IngestionService dependency not configured")


def _get_storage_service() -> StorageService:
    """Dependency placeholder for the StorageService.

    Overridden by app factory dependency_overrides or replaced
    at startup with the real configured instance.
    """
    raise NotImplementedError("StorageService dependency not configured")


def _get_base_analysis_service() -> BaseAnalysisService:
    """Dependency placeholder for the BaseAnalysisService.

    Overridden by app factory dependency_overrides at startup.
    """
    raise NotImplementedError("BaseAnalysisService dependency not configured")


# --- Size limits (bytes) for reference in error responses ---
_SIZE_LIMIT_TEXT = 1_048_576  # 1 MB
_SIZE_LIMIT_PDF = 10_485_760  # 10 MB

# Supported file extensions
_SUPPORTED_FORMATS = [".md", ".txt", ".pdf"]


def _error_code_from_message(error_message: str | None) -> str:
    """Infer the validation error code from the IngestionService error_message.

    The Validator already produces messages containing key phrases that allow
    reliable classification without coupling the API layer directly to the
    Validator's error_code field (which is not propagated through
    DocumentStatus).
    """
    if error_message is None:
        return "extraction_failed"

    msg_lower = error_message.lower()

    if "scanned" in msg_lower:
        return "scanned_pdf"
    if "not supported" in msg_lower or "unsupported" in msg_lower:
        return "unsupported_format"
    if "exceeds" in msg_lower or "too large" in msg_lower or "size" in msg_lower:
        return "file_too_large"
    if "utf-8" in msg_lower or "encoding" in msg_lower:
        return "invalid_encoding"

    return "extraction_failed"


def _build_error_response(error_code: str, message: str) -> dict:
    """Build the error response body with optional extra fields."""
    body: dict = {"error": error_code, "message": message}

    if error_code == "unsupported_format":
        body["supported_formats"] = _SUPPORTED_FORMATS
    elif error_code == "file_too_large":
        # Determine which limit applies from the message context
        if "pdf" in message.lower():
            body["max_size_bytes"] = _SIZE_LIMIT_PDF
        else:
            body["max_size_bytes"] = _SIZE_LIMIT_TEXT
    elif error_code == "invalid_encoding":
        body["required_encoding"] = "utf-8"

    return body


# --- Endpoints ---


@router.post(
    "/upload",
    response_model=DocumentStatus,
    status_code=202,
    responses={
        400: {"description": "Validation error"},
        422: {"description": "Extraction failure"},
    },
)
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    ingestion_service: IngestionService = Depends(_get_ingestion_service),
    storage_service: StorageService = Depends(_get_storage_service),
    base_analysis_service: BaseAnalysisService = Depends(_get_base_analysis_service),
):
    """Upload a document for ingestion.

    Accepts multipart file uploads (.md, .txt, .pdf).
    Returns 202 on success with the document status.
    Returns 400 for validation errors.
    Returns 422 for extraction failures.

    On successful ingestion, automatically triggers base analysis as a
    background task. The upload response returns immediately without waiting
    for analysis to complete. Analysis failure does not affect document status.
    """
    file_bytes = await file.read()
    filename = file.filename or "unnamed"
    content_type = file.content_type

    result: DocumentStatus = await ingestion_service.ingest(
        file_bytes=file_bytes,
        filename=filename,
        content_type=content_type,
    )

    if result.status == "failed":
        error_code = _error_code_from_message(result.error_message)
        error_message = result.error_message or "Processing failed"
        body = _build_error_response(error_code, error_message)

        # Validation errors → 400, extraction failures → 422
        if error_code in ("unsupported_format", "file_too_large", "invalid_encoding", "scanned_pdf"):
            return JSONResponse(status_code=400, content=body)
        else:
            return JSONResponse(status_code=422, content=body)

    # Trigger base analysis as a background task (fire-and-forget).
    # Analysis failure does not affect the document's ingestion status.
    background_tasks.add_task(
        _run_base_analysis,
        document_id=result.document_id,
        storage_service=storage_service,
        base_analysis_service=base_analysis_service,
    )

    return result


async def _run_base_analysis(
    document_id: str,
    storage_service: StorageService,
    base_analysis_service: BaseAnalysisService,
) -> None:
    """Execute base analysis in the background.

    Retrieves the IR from storage and runs the analysis service.
    All exceptions are caught and logged — analysis failure must never
    propagate or affect the document's ingestion status.
    """
    try:
        ir = await storage_service.get_ir(document_id)
        if ir is None:
            logger.warning(
                "Cannot run base analysis for document '%s': IR not available",
                document_id,
            )
            return
        await base_analysis_service.analyze(document_id, ir)
    except Exception as exc:
        logger.error(
            "Base analysis background task failed for document '%s': %s",
            document_id,
            str(exc),
            exc_info=True,
        )


@router.get(
    "/{document_id}/status",
    response_model=DocumentStatus,
    responses={404: {"description": "Document not found"}},
)
async def get_document_status(
    document_id: str,
    storage_service: StorageService = Depends(_get_storage_service),
):
    """Get the processing status of a document.

    Returns 200 with the document status if found.
    Returns 404 if the document does not exist.
    """
    status = await storage_service.get_status(document_id)

    if status is None:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "message": f"Document '{document_id}' not found"},
        )

    return status


@router.get(
    "/{document_id}/ir",
    response_model=IntermediateRepresentation,
    responses={
        404: {"description": "Document not found"},
        409: {"description": "Document not ready"},
    },
)
async def get_document_ir(
    document_id: str,
    storage_service: StorageService = Depends(_get_storage_service),
):
    """Retrieve the intermediate representation of a processed document.

    Returns 200 with the IR when the document is ready.
    Returns 404 if the document does not exist.
    Returns 409 if the document exists but is not ready (still processing or failed).
    """
    # First check if document exists
    status = await storage_service.get_status(document_id)

    if status is None:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "message": f"Document '{document_id}' not found"},
        )

    # Attempt to retrieve IR
    ir = await storage_service.get_ir(document_id)

    if ir is None:
        # Document exists but IR not available (processing or failed)
        return JSONResponse(
            status_code=409,
            content={
                "error": "not_ready",
                "message": f"Document '{document_id}' is not ready. Current status: {status.status}",
            },
        )

    return ir
