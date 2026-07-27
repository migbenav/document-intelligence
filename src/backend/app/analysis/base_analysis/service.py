"""BaseAnalysisService — orchestrates the full base analysis pipeline.

Coordinates LocalAnalyzer (deterministic structural analysis), LLMAnalyzer
(summary + classification via light model), and BaseAnalysisStorage (persistence)
to produce a DocumentCard for each ingested document.

Key behaviors:
- Idempotency: skips re-execution if a completed card with matching size_bytes exists.
- Graceful degradation: never raises exceptions; any failure produces a partial card.
- Retry: retry_llm re-executes only the LLM phase for an existing card.
- Outdated propagation: on re-upload (size mismatch), marks all on-demand analysis
  results as outdated via OnDemandAnalysisStorage.

Requirements covered: Req 1 (criteria 3, 4), Req 4 (criterion 4), Req 5 (criteria 1, 2, 3),
                      On-Demand Req 6 (criterion 6).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.analysis.base_analysis.llm_analyzer import LLMAnalyzer, LLMAnalysisResult
from app.analysis.base_analysis.local_analyzer import LocalAnalyzer, LocalAnalysisResult
from app.analysis.base_analysis.storage import BaseAnalysisStorage
from app.models.document import IntermediateRepresentation
from app.models.document_card import DocumentCard

if TYPE_CHECKING:
    from app.analysis.on_demand.storage import OnDemandAnalysisStorage

logger = logging.getLogger(__name__)


class CardNotFoundError(Exception):
    """Raised when retry_llm is called but no card exists for the document."""

    pass


class BaseAnalysisService:
    """Orchestrates the full base analysis pipeline.

    Combines local processing, LLM analysis, and persistence into a single
    workflow that produces a DocumentCard. Ensures idempotency and graceful
    degradation on any failure.
    """

    def __init__(
        self,
        local_analyzer: LocalAnalyzer,
        llm_analyzer: LLMAnalyzer,
        storage: BaseAnalysisStorage,
        on_demand_storage: OnDemandAnalysisStorage | None = None,
    ) -> None:
        """Initialize with analyzer and storage dependencies.

        Args:
            local_analyzer: Deterministic IR processor (no network calls).
            llm_analyzer: LLM-based summary/classification producer.
            storage: Persistence layer for DocumentCard.
            on_demand_storage: Optional on-demand analysis storage for
                outdated propagation on re-upload.
        """
        self._local_analyzer = local_analyzer
        self._llm_analyzer = llm_analyzer
        self._storage = storage
        self._on_demand_storage = on_demand_storage

    async def analyze(
        self,
        document_id: str,
        ir: IntermediateRepresentation,
        *,
        language: str = "es",
        model_override: str | None = None,
        auto_fallback: bool = True,
    ) -> DocumentCard:
        """Execute base analysis (local + LLM). Returns completed or partial card.

        Does not raise exceptions — all failures result in a partial card.

        Idempotency guard: if an existing card has status="completed" and its
        file_metadata.size_bytes matches the IR's metadata.size_bytes, the
        existing card is returned without re-execution.

        Args:
            document_id: UUID of the document to analyze.
            ir: The IntermediateRepresentation from ingestion.
            language: Language code for LLM response ('es' or 'en'). Defaults to 'es'.
            model_override: If provided, override the default model for LLM calls.
            auto_fallback: Whether to enable automatic fallback on transient errors.

        Returns:
            A DocumentCard with status "completed" or "partial".
        """
        try:
            # Idempotency check: return existing completed card if size matches
            existing_card = await self._storage.get_card(document_id)
            if (
                existing_card is not None
                and existing_card.status == "completed"
                and existing_card.file_metadata.size_bytes == ir.metadata.size_bytes
            ):
                return existing_card

            # Re-upload detection: if an existing card exists but size differs,
            # mark all on-demand analysis results as outdated (Req 6 criterion 6).
            if (
                existing_card is not None
                and existing_card.file_metadata.size_bytes != ir.metadata.size_bytes
                and self._on_demand_storage is not None
            ):
                try:
                    await self._on_demand_storage.mark_all_outdated(document_id)
                except Exception as exc:
                    logger.warning(
                        "Failed to mark on-demand analyses outdated for document '%s': %s",
                        document_id,
                        str(exc),
                    )

            # Step 1: Local processing (deterministic, always succeeds)
            local_result: LocalAnalysisResult = self._local_analyzer.analyze(ir)

            # Step 2: LLM processing (may return None on failure)
            llm_result: LLMAnalysisResult | None = await self._llm_analyzer.analyze(
                title=local_result.title,
                chunks=ir.chunks,
                organization_type=local_result.organization_type,
                language=language,
                model_override=model_override,
                auto_fallback=auto_fallback,
            )

            # Step 3: Build DocumentCard
            now = datetime.now(timezone.utc)
            card = self._build_card(
                document_id=document_id,
                local_result=local_result,
                llm_result=llm_result,
                existing_card=existing_card,
                now=now,
            )

            # Step 4: Persist
            await self._storage.upsert_card(card)

            return card

        except Exception as e:
            # Never raise — build a minimal partial card from whatever we have
            logger.error(
                "Unexpected error during base analysis for document '%s': %s",
                document_id,
                str(e),
                exc_info=True,
            )
            return await self._build_fallback_card(document_id, ir)

    async def retry_llm(
        self,
        document_id: str,
        ir: IntermediateRepresentation,
        *,
        language: str = "es",
        model_override: str | None = None,
        auto_fallback: bool = True,
    ) -> DocumentCard:
        """Re-execute only the LLM phase for an existing card.

        Loads the existing card, re-runs the LLM analyzer, updates the
        summary, classification, model_id, prompt_version, status, and
        updated_at fields, then persists.

        Args:
            document_id: UUID of the document whose card to retry.
            ir: The IntermediateRepresentation for context.
            language: Language code for LLM response ('es' or 'en'). Defaults to 'es'.
            model_override: If provided, override the default model for LLM calls.
            auto_fallback: Whether to enable automatic fallback on transient errors.

        Returns:
            The updated DocumentCard.

        Raises:
            CardNotFoundError: If no card exists for the given document_id.
        """
        existing_card = await self._storage.get_card(document_id)
        if existing_card is None:
            raise CardNotFoundError(
                f"No card exists for document '{document_id}'"
            )

        # Re-execute LLM
        llm_result: LLMAnalysisResult | None = await self._llm_analyzer.analyze(
            title=existing_card.title,
            chunks=ir.chunks,
            organization_type=existing_card.organization_type,
            language=language,
            model_override=model_override,
            auto_fallback=auto_fallback,
        )

        # Update card fields
        now = datetime.now(timezone.utc)
        if llm_result is not None:
            updated_card = existing_card.model_copy(
                update={
                    "summary": llm_result.summary,
                    "classification": llm_result.classification,
                    "model_id": llm_result.model_id,
                    "prompt_version": llm_result.prompt_version,
                    "status": "completed",
                    "updated_at": now,
                }
            )
        else:
            updated_card = existing_card.model_copy(
                update={
                    "status": "failed_llm",
                    "updated_at": now,
                }
            )

        await self._storage.upsert_card(updated_card)
        return updated_card

    def _build_card(
        self,
        document_id: str,
        local_result: LocalAnalysisResult,
        llm_result: LLMAnalysisResult | None,
        existing_card: DocumentCard | None,
        now: datetime,
    ) -> DocumentCard:
        """Build a DocumentCard from local and LLM results.

        If an existing card is present, reuse its id and created_at.
        Otherwise, generate a new UUID and set created_at to now.

        Args:
            document_id: The document UUID.
            local_result: Results from local processing.
            llm_result: Results from LLM processing (None if failed).
            existing_card: The previously persisted card, if any.
            now: Current UTC timestamp.

        Returns:
            A new DocumentCard instance.
        """
        card_id = existing_card.id if existing_card else str(uuid.uuid4())
        created_at = existing_card.created_at if existing_card else now

        if llm_result is not None:
            return DocumentCard(
                id=card_id,
                document_id=document_id,
                title=local_result.title,
                summary=llm_result.summary,
                classification=llm_result.classification,
                organization_type=local_result.organization_type,
                statistics=local_result.statistics,
                file_metadata=local_result.file_metadata,
                status="completed",
                outdated=False,
                model_id=llm_result.model_id,
                prompt_version=llm_result.prompt_version,
                created_at=created_at,
                updated_at=now,
            )
        else:
            return DocumentCard(
                id=card_id,
                document_id=document_id,
                title=local_result.title,
                summary=None,
                classification=None,
                organization_type=local_result.organization_type,
                statistics=local_result.statistics,
                file_metadata=local_result.file_metadata,
                status="partial",
                outdated=False,
                model_id=None,
                prompt_version=None,
                created_at=created_at,
                updated_at=now,
            )

    async def _build_fallback_card(
        self, document_id: str, ir: IntermediateRepresentation
    ) -> DocumentCard:
        """Build a minimal partial card when an unexpected error occurs.

        Attempts to run local processing. If even that fails, creates a
        card with the absolute minimum information available.

        Args:
            document_id: The document UUID.
            ir: The IntermediateRepresentation.

        Returns:
            A partial DocumentCard with whatever data can be assembled.
        """
        now = datetime.now(timezone.utc)
        try:
            local_result = self._local_analyzer.analyze(ir)
            card = DocumentCard(
                id=str(uuid.uuid4()),
                document_id=document_id,
                title=local_result.title,
                summary=None,
                classification=None,
                organization_type=local_result.organization_type,
                statistics=local_result.statistics,
                file_metadata=local_result.file_metadata,
                status="partial",
                outdated=False,
                model_id=None,
                prompt_version=None,
                created_at=now,
                updated_at=now,
            )
            await self._storage.upsert_card(card)
            return card
        except Exception as fallback_error:
            logger.error(
                "Fallback card creation also failed for document '%s': %s",
                document_id,
                str(fallback_error),
                exc_info=True,
            )
            # Return an absolute minimum card without persistence
            from app.models.document_card import (
                DocumentCardStatistics,
                FileMetadata,
                OrganizationType,
            )

            return DocumentCard(
                id=str(uuid.uuid4()),
                document_id=document_id,
                title=ir.metadata.original_filename,
                summary=None,
                classification=None,
                organization_type=OrganizationType.FREE_FORM,
                statistics=DocumentCardStatistics(
                    total_chunks=len(ir.chunks),
                    sections_detected=0,
                    hierarchy_levels=1,
                    has_existing_index=False,
                ),
                file_metadata=FileMetadata(
                    size_bytes=ir.metadata.size_bytes,
                    format=ir.metadata.format.value,
                    language=ir.metadata.language.value,
                ),
                status="partial",
                outdated=False,
                model_id=None,
                prompt_version=None,
                created_at=now,
                updated_at=now,
            )
