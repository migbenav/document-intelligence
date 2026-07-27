"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.analysis import (
    _get_analysis_service,
    router as analysis_router,
)
from app.api.v1.analyses import (
    _get_on_demand_analysis_service,
    _get_storage_service as _get_analyses_storage_service,
    router as analyses_router,
)
from app.api.v1.card import (
    _get_base_analysis_service,
    _get_base_analysis_storage,
    _get_storage_service as _get_card_storage_service,
    router as card_router,
)
from app.api.v1.documents import (
    _get_base_analysis_service as _get_documents_base_analysis_service,
    _get_ingestion_service,
    _get_storage_service,
    router as documents_router,
)
from app.api.v1.quality import (
    _get_analysis_storage_service,
    _get_quality_analysis_service,
    router as quality_router,
)
from app.api.v1.query import (
    _get_analysis_service as _get_query_analysis_service,
    _get_query_service,
    router as query_router,
)
from app.analysis.base_analysis.llm_analyzer import LLMAnalyzer
from app.analysis.base_analysis.local_analyzer import LocalAnalyzer
from app.analysis.base_analysis.service import BaseAnalysisService
from app.analysis.base_analysis.storage import BaseAnalysisStorage
from app.analysis.extraction import ExtractionService
from app.analysis.llm_client import LLMClient
from app.analysis.on_demand.conclusions_analyzer import ConclusionsAnalyzer
from app.analysis.on_demand.index_analyzer import IndexAnalyzer
from app.analysis.on_demand.questions_analyzer import QuestionsAnalyzer
from app.analysis.on_demand.relations_analyzer import RelationsAnalyzer
from app.analysis.on_demand.service import OnDemandAnalysisService
from app.analysis.on_demand.storage import OnDemandAnalysisStorage
from app.analysis.quality.ambiguity_detector import AmbiguityDetector
from app.analysis.quality.completeness_evaluator import CompletenessEvaluator
from app.analysis.quality.contradiction_detector import ContradictionDetector
from app.analysis.quality.finding_verifier import FindingVerifier
from app.analysis.quality.service import QualityAnalysisService
from app.analysis.quality.suggestion_generator import SuggestionGenerator
from app.analysis.query.context_builder import ContextBuilder
from app.analysis.query.evidence_verifier import QueryEvidenceVerifier
from app.analysis.query.response_parser import ResponseParser
from app.analysis.query.service import QueryService
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

        # Quality analysis service dependencies
        contradiction_detector = ContradictionDetector(llm_client=llm_client)
        ambiguity_detector = AmbiguityDetector(llm_client=llm_client)
        completeness_evaluator = CompletenessEvaluator(llm_client=llm_client)
        suggestion_generator = SuggestionGenerator(llm_client=llm_client)
        finding_verifier = FindingVerifier()

        quality_analysis_service = QualityAnalysisService(
            contradiction_detector=contradiction_detector,
            ambiguity_detector=ambiguity_detector,
            completeness_evaluator=completeness_evaluator,
            suggestion_generator=suggestion_generator,
            finding_verifier=finding_verifier,
            storage=analysis_storage_service,
        )

        app.dependency_overrides[_get_quality_analysis_service] = (
            lambda: quality_analysis_service
        )
        app.dependency_overrides[_get_analysis_storage_service] = (
            lambda: analysis_storage_service
        )

        # Query service dependencies
        context_builder = ContextBuilder(llm_client=llm_client)
        response_parser = ResponseParser()
        evidence_verifier = QueryEvidenceVerifier()

        query_service = QueryService(
            llm_client=llm_client,
            context_builder=context_builder,
            response_parser=response_parser,
            evidence_verifier=evidence_verifier,
        )

        app.dependency_overrides[_get_query_service] = lambda: query_service
        app.dependency_overrides[_get_query_analysis_service] = lambda: analysis_service

        # Base analysis service dependencies
        local_analyzer = LocalAnalyzer()
        llm_analyzer = LLMAnalyzer(llm_client=llm_client)
        base_analysis_storage = BaseAnalysisStorage(supabase_client)
        on_demand_analysis_storage = OnDemandAnalysisStorage(supabase_client)

        base_analysis_service = BaseAnalysisService(
            local_analyzer=local_analyzer,
            llm_analyzer=llm_analyzer,
            storage=base_analysis_storage,
            on_demand_storage=on_demand_analysis_storage,
        )

        app.dependency_overrides[_get_base_analysis_service] = (
            lambda: base_analysis_service
        )
        app.dependency_overrides[_get_base_analysis_storage] = (
            lambda: base_analysis_storage
        )
        app.dependency_overrides[_get_card_storage_service] = lambda: storage_service
        app.dependency_overrides[_get_documents_base_analysis_service] = (
            lambda: base_analysis_service
        )

        # On-demand analysis service dependencies
        index_analyzer = IndexAnalyzer(llm_client=llm_client)
        relations_analyzer = RelationsAnalyzer(llm_client=llm_client)
        questions_analyzer = QuestionsAnalyzer(llm_client=llm_client)
        conclusions_analyzer = ConclusionsAnalyzer(llm_client=llm_client)

        on_demand_analysis_service = OnDemandAnalysisService(
            index_analyzer=index_analyzer,
            relations_analyzer=relations_analyzer,
            questions_analyzer=questions_analyzer,
            conclusions_analyzer=conclusions_analyzer,
            storage=on_demand_analysis_storage,
            ingestion_storage=storage_service,
        )

        app.dependency_overrides[_get_on_demand_analysis_service] = (
            lambda: on_demand_analysis_service
        )
        app.dependency_overrides[_get_analyses_storage_service] = (
            lambda: storage_service
        )

    # --- Router registration ---
    app.include_router(documents_router, prefix="/api/v1/documents", tags=["documents"])
    app.include_router(analysis_router, prefix="/api/v1/documents", tags=["analysis"])
    app.include_router(analyses_router, prefix="/api/v1/documents", tags=["analyses"])
    app.include_router(quality_router, prefix="/api/v1/documents", tags=["quality"])
    app.include_router(query_router, prefix="/api/v1/documents", tags=["query"])
    app.include_router(card_router, prefix="/api/v1/documents", tags=["card"])

    return app
