"""OnDemandAnalysisService — orchestrator for on-demand analyses.

Coordinates idempotency checks, analyzer dispatch, and result persistence
for all four on-demand analysis types. Does not perform LLM calls itself;
it delegates to the individual analyzers.

Requirements covered: Req 6 (criteria 1-8), Req 7 (criteria 2, 3)
"""

import logging
import uuid
from datetime import datetime, timezone

from app.analysis.on_demand.conclusions_analyzer import ConclusionsAnalyzer
from app.analysis.on_demand.index_analyzer import IndexAnalyzer
from app.analysis.on_demand.models import (
    AnalysisRecord,
    AnalysisStatus,
    AnalysisType,
    IndexResult,
)
from app.analysis.on_demand.questions_analyzer import QuestionsAnalyzer
from app.analysis.on_demand.relations_analyzer import RelationsAnalyzer
from app.analysis.on_demand.storage import OnDemandAnalysisStorage
from app.ingestion.storage import StorageService

logger = logging.getLogger(__name__)


class DocumentIRNotAvailableError(Exception):
    """Raised when the document's IR is not available (not ingested or not ready)."""

    pass


class OnDemandAnalysisService:
    """Orchestrates on-demand analysis execution, idempotency, and persistence.

    This service:
    1. Checks storage for existing completed (non-outdated) results (idempotency).
    2. Loads the document IR from ingestion storage.
    3. Routes to the correct analyzer based on analysis_type.
    4. Persists successful results and returns them.
    5. Lets exceptions propagate on failure (the API endpoint handles errors).
    """

    def __init__(
        self,
        index_analyzer: IndexAnalyzer,
        relations_analyzer: RelationsAnalyzer,
        questions_analyzer: QuestionsAnalyzer,
        conclusions_analyzer: ConclusionsAnalyzer,
        storage: OnDemandAnalysisStorage,
        ingestion_storage: StorageService,
    ) -> None:
        """Initialize with all required dependencies.

        Args:
            index_analyzer: Analyzer for Build Index (C3.1).
            relations_analyzer: Analyzer for Section Relations (C3.2).
            questions_analyzer: Analyzer for Questions Answered (C3.3).
            conclusions_analyzer: Analyzer for Conclusions & Recommendations (C3.4).
            storage: Persistence layer for analysis results.
            ingestion_storage: Storage service to load the document IR.
        """
        self._index_analyzer = index_analyzer
        self._relations_analyzer = relations_analyzer
        self._questions_analyzer = questions_analyzer
        self._conclusions_analyzer = conclusions_analyzer
        self._storage = storage
        self._ingestion_storage = ingestion_storage

    async def execute(
        self,
        document_id: str,
        analysis_type: AnalysisType,
        preferences: dict,
    ) -> AnalysisRecord:
        """Execute an on-demand analysis or return cached result.

        Flow:
        1. Check storage for existing completed non-outdated result → return if found.
        2. Load IR from ingestion_storage → raise if not available.
        3. Route to correct analyzer based on analysis_type.
        4. For section_relations: check if build_index result exists, pass to analyzer.
        5. On success: build AnalysisRecord with status=COMPLETED, persist, return.
        6. On failure: let exception propagate (endpoint handles error response).

        Args:
            document_id: UUID of the document to analyze.
            analysis_type: Which analysis to run.
            preferences: Dict with keys:
                - language (str): UI language for the response.
                - model_override (str | None): Optional model to use.
                - auto_fallback (bool): Whether to allow automatic fallback.
                - document_language (str | None): Document language (for conclusions).

        Returns:
            AnalysisRecord with status=COMPLETED and the result.

        Raises:
            DocumentIRNotAvailableError: If the document IR is not available.
            IndexAnalysisError: If Build Index fails.
            RelationsAnalysisError: If Section Relations fails.
            QuestionsAnalysisError: If Questions Answered fails.
            ValueError: If Conclusions fails.
            asyncio.TimeoutError: If the LLM call times out.
        """
        # 1. Check for existing completed, non-outdated result (idempotency)
        existing = await self._storage.get_result(document_id, analysis_type)
        if existing is not None and existing.status == AnalysisStatus.COMPLETED:
            logger.info(
                "Returning cached analysis result",
                extra={
                    "document_id": document_id,
                    "analysis_type": analysis_type.value,
                },
            )
            return existing

        # 2. Load IR from ingestion storage
        ir = await self._ingestion_storage.get_ir(document_id)
        if ir is None:
            raise DocumentIRNotAvailableError(
                f"IR not available for document {document_id}. "
                "Document may not be ingested or processing is incomplete."
            )

        # 3. Extract preferences
        language = preferences.get("language", "es")
        model_override = preferences.get("model_override")
        auto_fallback = preferences.get("auto_fallback", True)
        document_language = preferences.get("document_language")

        # 4. Route to correct analyzer and execute
        result, prompt_version, model_id = await self._dispatch_analyzer(
            analysis_type=analysis_type,
            ir=ir,
            language=language,
            model_override=model_override,
            auto_fallback=auto_fallback,
            document_id=document_id,
            document_language=document_language,
        )

        # 5. Build AnalysisRecord with status=COMPLETED, persist, return
        now = datetime.now(timezone.utc)
        record = AnalysisRecord(
            id=str(uuid.uuid4()),
            document_id=document_id,
            analysis_type=analysis_type,
            status=AnalysisStatus.COMPLETED,
            result=result.model_dump() if hasattr(result, "model_dump") else result,
            model_id=model_id,
            prompt_version=prompt_version,
            error_message=None,
            created_at=now,
            updated_at=now,
        )

        await self._storage.save_result(record)

        logger.info(
            "Analysis completed and persisted",
            extra={
                "document_id": document_id,
                "analysis_type": analysis_type.value,
                "model_id": model_id,
            },
        )

        return record

    async def get_result(
        self, document_id: str, analysis_type: AnalysisType
    ) -> AnalysisRecord | None:
        """Retrieve a stored analysis result.

        Args:
            document_id: UUID of the document.
            analysis_type: Which analysis type to retrieve.

        Returns:
            AnalysisRecord if found, None if no result exists.
        """
        return await self._storage.get_result(document_id, analysis_type)

    async def get_all_statuses(self, document_id: str) -> dict[str, dict]:
        """Get the status summary for all analysis types of a document.

        Args:
            document_id: UUID of the document.

        Returns:
            Dict mapping analysis type value to {status, updated_at} dict.
        """
        return await self._storage.get_all_statuses(document_id)

    async def _dispatch_analyzer(
        self,
        analysis_type: AnalysisType,
        ir,
        language: str,
        model_override: str | None,
        auto_fallback: bool,
        document_id: str,
        document_language: str | None,
    ) -> tuple:
        """Route to the correct analyzer and return (result, prompt_version, model_id).

        For section_relations: checks if build_index result exists in storage
        and passes it to the RelationsAnalyzer if available.

        Returns:
            Tuple of (typed_result, prompt_version, model_id).
        """
        if analysis_type == AnalysisType.BUILD_INDEX:
            result = await self._index_analyzer.analyze(
                ir=ir,
                language=language,
                model_override=model_override,
                auto_fallback=auto_fallback,
            )
            return result, self._index_analyzer.prompt_version, model_override

        elif analysis_type == AnalysisType.SECTION_RELATIONS:
            # Check if build_index result exists to enrich the relations prompt
            index_result = await self._get_index_result(document_id)

            result = await self._relations_analyzer.analyze(
                ir=ir,
                language=language,
                model_override=model_override,
                auto_fallback=auto_fallback,
                index_result=index_result,
            )
            return result, self._relations_analyzer.prompt_version, model_override

        elif analysis_type == AnalysisType.QUESTIONS_ANSWERED:
            result = await self._questions_analyzer.analyze(
                ir=ir,
                language=language,
                model_override=model_override,
                auto_fallback=auto_fallback,
            )
            return result, self._questions_analyzer.prompt_version, model_override

        elif analysis_type == AnalysisType.CONCLUSIONS:
            # Conclusions needs both ui_language and document_language
            doc_lang = document_language or language
            result = await self._conclusions_analyzer.analyze(
                ir=ir,
                language=language,
                document_language=doc_lang,
                model_override=model_override,
                auto_fallback=auto_fallback,
            )
            return result, self._conclusions_analyzer.PROMPT_VERSION, model_override

        else:
            raise ValueError(f"Unknown analysis type: {analysis_type}")

    async def _get_index_result(self, document_id: str) -> IndexResult | None:
        """Check if a completed build_index result exists and parse it.

        Args:
            document_id: UUID of the document.

        Returns:
            IndexResult if a completed build_index exists, None otherwise.
        """
        index_record = await self._storage.get_result(
            document_id, AnalysisType.BUILD_INDEX
        )

        if (
            index_record is not None
            and index_record.status == AnalysisStatus.COMPLETED
            and index_record.result is not None
        ):
            try:
                return IndexResult.model_validate(index_record.result)
            except Exception as e:
                logger.warning(
                    "Failed to parse stored build_index result for relations enrichment",
                    extra={
                        "document_id": document_id,
                        "error": str(e),
                    },
                )
                return None

        return None
