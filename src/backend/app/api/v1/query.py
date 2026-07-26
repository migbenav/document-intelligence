"""Query API endpoint: submit natural language questions about a document.

Provides:
- POST /{document_id}/query — processes a question against the Knowledge Model (Req 5.1–5.6, 1.7, 1.8)
"""

import asyncio
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.analysis.query.service import QueryError, QueryService
from app.analysis.service import AnalysisService
from app.models.query import QueryRequest

logger = logging.getLogger(__name__)

router = APIRouter()

# Total timeout for query processing at the API layer (seconds)
_QUERY_TIMEOUT_SECONDS = 30


# --- Dependency injection helpers ---


def _get_analysis_service() -> AnalysisService:
    """Dependency placeholder for the AnalysisService.

    Overridden by app factory dependency_overrides at startup
    with the fully constructed service instance.
    """
    raise NotImplementedError("AnalysisService dependency not configured")


def _get_query_service() -> QueryService:
    """Dependency placeholder for the QueryService.

    Overridden by app factory dependency_overrides at startup
    with the fully constructed service instance.
    """
    raise NotImplementedError("QueryService dependency not configured")


# --- Endpoint ---


@router.post(
    "/{document_id}/query",
    status_code=200,
    responses={
        404: {"description": "Document not found"},
        409: {"description": "Knowledge Model not completed"},
        422: {"description": "Validation error (question length)"},
        500: {"description": "Query processing failed"},
    },
)
async def query_document(
    document_id: str,
    body: QueryRequest,
    analysis_service: AnalysisService = Depends(_get_analysis_service),
    query_service: QueryService = Depends(_get_query_service),
):
    """Submit a natural language question about a document.

    Processes the question against the document's completed Knowledge Model
    and returns a structured answer with evidence references.

    Returns 200 with QueryResponse on success.
    Returns 404 if the document does not exist (Req 5.3).
    Returns 409 if the Knowledge Model is not completed (Req 5.2).
    Returns 422 if the question fails validation (Req 5.4).
    Returns 500 on LLM error, timeout, or parse failure (Req 5.5).
    """
    # Check document/session exists
    session = await analysis_service.get_session(document_id)
    if session is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "not_found",
                "message": f"No analysis session found for document '{document_id}'.",
            },
        )

    # Check analysis is completed (Req 1.7, 5.2)
    if session.status != "completed":
        return JSONResponse(
            status_code=409,
            content={
                "error": "km_not_completed",
                "message": (
                    f"Queries require a completed Knowledge Model. "
                    f"Current analysis status: {session.status}."
                ),
            },
        )

    # Load Knowledge Model and IR
    knowledge_model = await analysis_service.get_knowledge_model_object(document_id)
    ir = await analysis_service.get_ir(document_id)

    if knowledge_model is None or ir is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "not_found",
                "message": f"Knowledge model or IR not found for document '{document_id}'.",
            },
        )

    # Process query with timeout (Req 5.6)
    try:
        response = await asyncio.wait_for(
            query_service.answer(
                document_id=document_id,
                question=body.question,
                knowledge_model=knowledge_model,
                ir=ir,
            ),
            timeout=_QUERY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=500,
            content={
                "error": "query_failed",
                "message": "Query processing timed out.",
            },
        )
    except QueryError as e:
        # Determine error code based on the error message
        error_message = str(e)
        if "parse" in error_message.lower():
            error_code = "response_parse_error"
            content = {
                "error": error_code,
                "message": "Failed to parse LLM response after retry.",
                "question": body.question,
            }
        else:
            error_code = "query_failed"
            content = {
                "error": error_code,
                "message": "Query processing failed.",
            }
        return JSONResponse(status_code=500, content=content)
    except Exception:
        # Catch-all: do not expose internal stack traces (Req 5.5)
        logger.exception("Unexpected error during query processing")
        return JSONResponse(
            status_code=500,
            content={
                "error": "query_failed",
                "message": "An internal error occurred during query processing.",
            },
        )

    # Return successful response
    return JSONResponse(
        status_code=200,
        content=response.model_dump(mode="json"),
    )
