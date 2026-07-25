"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.analysis import (
    _get_analysis_service,
    router as analysis_router,
)
from app.api.v1.documents import (
    _get_ingestion_service,
    _get_storage_service,
    router as documents_router,
)
from app.analysis.extraction import ExtractionService
from app.analysis.llm_client import LLMClient
from app.analysis.service import AnalysisService, AnalysisStorageService
from app.analysis.type_inference import TypeInferenceService
from app.analysis.verification import VerificationService
from app.ingestion.adapters.markdown_adapter import MarkdownAdapter
from app.ingestion.adapters.pdf_adapter import PdfAdapter
from app.ingestion.adapters.plaintext_adapter import PlainTextAdapter
from app.ingestion.ir_builder import IRBuilder
from app.ingestion.language import LanguageDetector
from app.ingestion.service import IngestionService
from app.ingestion.storage import StorageService
from app.ingestion.validator import Validator


def create_app(
    *,
    supabase_client=None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        supabase_client: Optional pre-configured Supabase client.
            If None, routes requiring storage will raise on first use.
        cors_origins: Allowed CORS origins. Defaults to ["*"] for development.

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(
        title="Document Intelligence API",
        version="0.1.0",
        description="Document ingestion and analysis API",
    )

    # --- CORS middleware ---
    allowed_origins = cors_origins or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Dependency injection ---
    if supabase_client is not None:
        storage_service = StorageService(supabase_client)

        ingestion_service = IngestionService(
            validator=Validator(),
            adapters=[MarkdownAdapter(), PlainTextAdapter(), PdfAdapter()],
            language_detector=LanguageDetector(),
            ir_builder=IRBuilder(),
            storage_service=storage_service,
        )

        app.dependency_overrides[_get_ingestion_service] = lambda: ingestion_service
        app.dependency_overrides[_get_storage_service] = lambda: storage_service

        # Analysis service dependencies
        llm_client = LLMClient()
        type_inference_service = TypeInferenceService(llm_client=llm_client)
        extraction_service = ExtractionService(llm_client=llm_client)
        verification_service = VerificationService()
        analysis_storage_service = AnalysisStorageService(supabase_client)

        analysis_service = AnalysisService(
            type_inference_service=type_inference_service,
            extraction_service=extraction_service,
            verification_service=verification_service,
            storage=analysis_storage_service,
        )

        app.dependency_overrides[_get_analysis_service] = lambda: analysis_service

    # --- Router registration ---
    app.include_router(documents_router, prefix="/api/v1/documents", tags=["documents"])
    app.include_router(analysis_router, prefix="/api/v1/documents", tags=["analysis"])

    return app
