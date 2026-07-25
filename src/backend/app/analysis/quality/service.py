"""Quality analysis pipeline orchestrator.

Coordinates the full quality analysis pipeline: contradiction detection,
ambiguity detection, completeness evaluation, suggestion generation,
and finding verification. Manages session state transitions and timeout.

Requirements covered: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 8.1, 8.2, 8.3, 8.5, 8.6, 9.3, 9.4
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from app.analysis.prompts import (
    ambiguity_detection_v1,
    completeness_evaluation_v1,
    contradiction_detection_v1,
    suggestion_generation_v1,
)
from app.analysis.quality.ambiguity_detector import AmbiguityDetector
from app.analysis.quality.completeness_evaluator import CompletenessEvaluator
from app.analysis.quality.contradiction_detector import ContradictionDetector
from app.analysis.quality.finding_verifier import FindingVerifier
from app.analysis.quality.suggestion_generator import SuggestionGenerator
from app.analysis.service import AnalysisStorageService
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    IntermediateRepresentation,
)
from app.models.knowledge_model import KnowledgeModel
from app.models.quality_analysis import (
    Inconsistency,
    QualityAnalysisMetadata,
    QualityAnalysisResult,
)

logger = logging.getLogger(__name__)

# Pipeline timeout in seconds (Req 6.7)
PIPELINE_TIMEOUT_SECONDS = 120.0


class QualityAnalysisError(Exception):
    """Base error for quality analysis failures."""

    pass


class KMNotCompletedError(QualityAnalysisError):
    """Raised when quality analysis is triggered before KM is completed (Req 8.1)."""

    pass


class AnalysisInProgressError(QualityAnalysisError):
    """Raised when quality analysis is already in progress for this document."""

    pass


class QualityAnalysisService:
    """Orchestrates the complete quality analysis pipeline.

    Pipeline steps:
    1. ContradictionDetector.detect() — structural + LLM contradictions
    2. AmbiguityDetector.detect() — LLM-based ambiguity findings
    3. CompletenessEvaluator.evaluate() — schema-based missing elements
    4. SuggestionGenerator.generate() — improvement suggestions
    5. FindingVerifier.verify_all() — evidence verification
    6. Mark elements with involves_unverified_elements (Req 8.4)

    On success: persist results, set quality_status = "completed"
    On failure: preserve explicit-relationship contradictions, clear all other
    partial results, set quality_status = "failed" (Req 6.4)
    """

    def __init__(
        self,
        contradiction_detector: ContradictionDetector,
        ambiguity_detector: AmbiguityDetector,
        completeness_evaluator: CompletenessEvaluator,
        suggestion_generator: SuggestionGenerator,
        finding_verifier: FindingVerifier,
        storage: AnalysisStorageService,
    ) -> None:
        """Initialize with all pipeline dependencies.

        Args:
            contradiction_detector: Detects contradictions from KM relationships + LLM.
            ambiguity_detector: Detects ambiguous statements using LLM.
            completeness_evaluator: Evaluates completeness against type schemas.
            suggestion_generator: Generates improvement suggestions from findings.
            finding_verifier: Verifies evidence text spans in findings.
            storage: Storage interface for session persistence.
        """
        self._contradiction_detector = contradiction_detector
        self._ambiguity_detector = ambiguity_detector
        self._completeness_evaluator = completeness_evaluator
        self._suggestion_generator = suggestion_generator
        self._finding_verifier = finding_verifier
        self._storage = storage

    async def run_analysis(self, document_id: str) -> QualityAnalysisResult:
        """Run the full quality analysis pipeline.

        Prerequisites: completed KM (Req 8.1).
        Timeout: 120 seconds (Req 6.7).

        Args:
            document_id: The document to analyze.

        Returns:
            QualityAnalysisResult with findings and metadata.

        Raises:
            KMNotCompletedError: Analysis session not completed (Req 8.1).
            AnalysisInProgressError: Quality analysis already running.
            asyncio.TimeoutError: Pipeline exceeded 120 seconds (Req 6.7).
        """
        # Prerequisite check: verify analysis session exists and status = "completed" (Req 8.1)
        session = self._storage.get_session_by_document(document_id)
        if session is None or session.get("status") != "completed":
            current_status = session.get("status") if session else "not_found"
            raise KMNotCompletedError(
                f"Quality analysis requires a completed Knowledge Model. "
                f"Current analysis status: {current_status}."
            )

        # If quality_status = "analyzing": raise error (analysis already in progress)
        if session.get("quality_status") == "analyzing":
            raise AnalysisInProgressError(
                "Quality analysis is already running for this document. "
                "Wait for it to complete or fail before re-triggering."
            )

        session_id = session["id"]

        # Create/reset quality analysis record: set quality_status = "analyzing",
        # quality_started_at = now(), clear previous results (Req 6.6)
        started_at = datetime.now(timezone.utc)
        self._storage.update_session(
            session_id,
            quality_status="analyzing",
            quality_started_at=started_at.isoformat(),
            quality_completed_at=None,
            quality_analysis=None,
            quality_error_message=None,
        )

        # Execute pipeline with 120-second timeout (Req 6.7)
        try:
            result = await asyncio.wait_for(
                self._execute_pipeline(document_id, session, session_id, started_at),
                timeout=PIPELINE_TIMEOUT_SECONDS,
            )
            return result
        except asyncio.TimeoutError:
            # On timeout: mark as failed with asyncio.shield() for cleanup (Req 6.7)
            await asyncio.shield(
                self._mark_failed(
                    document_id,
                    session_id,
                    "Quality analysis timed out after 120 seconds",
                    "timeout",
                )
            )
            raise
        except (KMNotCompletedError, AnalysisInProgressError):
            raise
        except Exception as e:
            # On failure: mark as failed
            await asyncio.shield(
                self._mark_failed(
                    document_id,
                    session_id,
                    str(e)[:1000],
                    "unknown",
                )
            )
            raise

    async def get_results(self, document_id: str) -> QualityAnalysisResult | None:
        """Retrieve existing quality analysis results (idempotent, Req 5.8).

        Args:
            document_id: The document to get results for.

        Returns:
            QualityAnalysisResult if analysis has been run, None otherwise.
        """
        session = self._storage.get_session_by_document(document_id)
        if session is None:
            return None

        quality_analysis = session.get("quality_analysis")
        if quality_analysis is None:
            return None

        # Deserialize from JSONB
        if isinstance(quality_analysis, str):
            quality_analysis = json.loads(quality_analysis)

        return QualityAnalysisResult.model_validate(quality_analysis)

    async def _execute_pipeline(
        self,
        document_id: str,
        session: dict,
        session_id: str,
        started_at: datetime,
    ) -> QualityAnalysisResult:
        """Execute the full quality analysis pipeline.

        Steps:
        1. Load KM and IR
        2. Detect contradictions (structural + LLM)
        3. Detect ambiguities (LLM)
        4. Evaluate completeness (schema-based + LLM for partial)
        5. Generate suggestions (LLM)
        6. Verify all finding evidence (deterministic)
        7. Mark elements with involves_unverified_elements
        8. Persist results and metadata

        Args:
            document_id: Document being analyzed.
            session: The analysis session row dict.
            session_id: The session ID for DB updates.
            started_at: Pipeline start timestamp.

        Returns:
            The completed QualityAnalysisResult.
        """
        # Load Knowledge Model from session
        km = KnowledgeModel.model_validate(session["knowledge_model"])

        # Load IR from storage
        ir = self._build_ir(document_id)

        # Get document type from session
        document_type = session.get("confirmed_type", "generic")

        # --- Step 1: Contradiction Detection ---
        self._storage.update_session(session_id, quality_status="analyzing_contradictions")

        try:
            inconsistencies = await self._contradiction_detector.detect(km, ir)
        except Exception as e:
            # Preserve explicit-relationship contradictions on failure (Req 6.4)
            await self._mark_failed(
                document_id,
                session_id,
                f"Contradiction detection failed: {e}"[:1000],
                "analyzing_contradictions",
            )
            raise

        # --- Step 2: Ambiguity Detection ---
        self._storage.update_session(session_id, quality_status="analyzing_ambiguities")

        try:
            ambiguities = await self._ambiguity_detector.detect(km, ir)
            inconsistencies.extend(ambiguities)
        except Exception as e:
            await self._mark_failed(
                document_id,
                session_id,
                f"Ambiguity detection failed: {e}"[:1000],
                "analyzing_ambiguities",
            )
            raise

        # --- Step 3: Completeness Evaluation ---
        self._storage.update_session(session_id, quality_status="analyzing_completeness")

        try:
            missing_elements = await self._completeness_evaluator.evaluate(
                km, document_type
            )
        except Exception as e:
            await self._mark_failed(
                document_id,
                session_id,
                f"Completeness evaluation failed: {e}"[:1000],
                "analyzing_completeness",
            )
            raise

        # --- Step 4: Suggestion Generation ---
        self._storage.update_session(session_id, quality_status="generating_suggestions")

        try:
            suggestions = await self._suggestion_generator.generate(
                inconsistencies, missing_elements, km, ir
            )
        except Exception as e:
            await self._mark_failed(
                document_id,
                session_id,
                f"Suggestion generation failed: {e}"[:1000],
                "generating_suggestions",
            )
            raise

        # --- Step 5: Finding Verification (deterministic) ---
        try:
            inconsistencies, suggestions = self._finding_verifier.verify_all(
                inconsistencies, suggestions, ir
            )
        except Exception as e:
            await self._mark_failed(
                document_id,
                session_id,
                f"Finding verification failed: {e}"[:1000],
                "verifying_evidence",
            )
            raise

        # --- Step 6: Mark elements with involves_unverified_elements (Req 8.4) ---
        # This is already handled by individual detectors, but we ensure it's set
        # on all findings that reference unverified KM elements.
        unverified_element_ids = {
            elem.id for elem in km.elements if not elem.verified
        }
        inconsistencies = self._mark_unverified_involvement(
            inconsistencies, unverified_element_ids
        )

        # --- Build result and metadata ---
        completed_at = datetime.now(timezone.utc)

        # Count findings by type
        contradictions_count = sum(
            1 for i in inconsistencies if i.type == "contradiction"
        )
        ambiguities_count = sum(
            1 for i in inconsistencies if i.type == "ambiguity"
        )

        metadata = QualityAnalysisMetadata(
            prompt_versions={
                "contradiction_detection": contradiction_detection_v1.VERSION,
                "ambiguity_detection": ambiguity_detection_v1.VERSION,
                "completeness_evaluation": completeness_evaluation_v1.VERSION,
                "suggestion_generation": suggestion_generation_v1.VERSION,
            },
            model_id=self._get_model_id(),
            temperature=0.1,
            document_type=document_type,
            started_at=started_at,
            completed_at=completed_at,
            finding_counts={
                "contradictions": contradictions_count,
                "ambiguities": ambiguities_count,
                "missing_elements": len(missing_elements),
                "suggestions": len(suggestions),
            },
        )

        result = QualityAnalysisResult(
            document_id=document_id,
            status="completed",
            inconsistencies=inconsistencies,
            missing_elements=missing_elements,
            suggestions=suggestions,
            metadata=metadata,
        )

        # Persist results as JSONB and mark completed (Req 6.3)
        result_json = result.model_dump(mode="json")
        self._storage.update_session(
            session_id,
            quality_status="completed",
            quality_completed_at=completed_at.isoformat(),
            quality_analysis=result_json,
            quality_error_message=None,
        )

        return result

    async def _mark_failed(
        self,
        document_id: str,
        session_id: str,
        error_message: str,
        error_phase: str,
    ) -> None:
        """Mark quality analysis as failed, preserving explicit contradictions (Req 6.4).

        On failure:
        - Preserve explicit-relationship contradictions as partial results
        - Clear all other partial results
        - Set quality_status = "failed" with error message

        Args:
            document_id: The document being analyzed.
            session_id: The session ID for DB update.
            error_message: Error description (max 1000 chars).
            error_phase: The pipeline phase where failure occurred.
        """
        try:
            # Build a failed result preserving only explicit contradictions
            # Attempt to re-collect structural contradictions if possible
            session = self._storage.get_session_by_document(document_id)
            explicit_contradictions: list[Inconsistency] = []

            if session and session.get("knowledge_model"):
                try:
                    km = KnowledgeModel.model_validate(session["knowledge_model"])
                    # Collect structural contradictions only (no LLM call)
                    explicit_contradictions = (
                        self._contradiction_detector._collect_structural_contradictions(km)
                    )
                except Exception:
                    pass  # If we can't collect them, proceed without

            # Build failed result with only explicit contradictions (Req 6.4)
            failed_result = QualityAnalysisResult(
                document_id=document_id,
                status="failed",
                inconsistencies=explicit_contradictions,
                missing_elements=[],
                suggestions=[],
                metadata=None,
                error_message=error_message[:1000],
                error_phase=error_phase,
            )

            result_json = failed_result.model_dump(mode="json")

            self._storage.update_session(
                session_id,
                quality_status="failed",
                quality_analysis=result_json,
                quality_error_message=error_message[:1000],
                quality_completed_at=None,
            )
        except Exception as cleanup_error:
            logger.error(
                "Failed to mark quality analysis as failed: %s",
                cleanup_error,
                extra={"session_id": session_id, "original_error": error_message},
            )

    def _build_ir(self, document_id: str) -> IntermediateRepresentation:
        """Build the IntermediateRepresentation from storage.

        Replicates the IR retrieval logic from AnalysisService._get_ir().

        Args:
            document_id: The document to retrieve IR for.

        Returns:
            The IntermediateRepresentation for the document.

        Raises:
            QualityAnalysisError: If document or chunks not found.
        """
        doc = self._storage.get_document(document_id)
        if doc is None:
            raise QualityAnalysisError(f"Document '{document_id}' not found.")

        chunks_data = self._storage.get_ir(document_id)
        if chunks_data is None:
            chunks_data = []

        # Parse warnings
        warnings = doc.get("warnings", [])
        if isinstance(warnings, str):
            warnings = json.loads(warnings)

        metadata = DocumentMetadata(
            original_filename=doc["original_filename"],
            format=DocumentFormat(doc["format"]),
            size_bytes=doc["size_bytes"],
            language=DetectedLanguage(doc.get("language", "unknown")),
            upload_timestamp=datetime.fromisoformat(doc["upload_timestamp"]),
            warnings=warnings,
        )

        chunks = [
            ContentChunkModel(
                chunk_id=c["chunk_id"],
                text=c["text"],
                structural_context=(
                    json.loads(c["structural_context"])
                    if isinstance(c["structural_context"], str)
                    else c["structural_context"]
                ),
                order=c["order"],
            )
            for c in chunks_data
        ]

        return IntermediateRepresentation(
            document_id=document_id,
            metadata=metadata,
            chunks=chunks,
        )

    def _mark_unverified_involvement(
        self,
        inconsistencies: list[Inconsistency],
        unverified_element_ids: set[str],
    ) -> list[Inconsistency]:
        """Ensure involves_unverified_elements is set on findings referencing unverified KM elements.

        Args:
            inconsistencies: The list of inconsistency findings.
            unverified_element_ids: Set of KM element IDs that are unverified.

        Returns:
            Updated inconsistencies with involves_unverified_elements set.
        """
        if not unverified_element_ids:
            return inconsistencies

        result = []
        for inc in inconsistencies:
            involves_unverified = any(
                eid in unverified_element_ids for eid in inc.affected_element_ids
            )
            if involves_unverified and not inc.involves_unverified_elements:
                inc = inc.model_copy(update={"involves_unverified_elements": True})
            result.append(inc)
        return result

    def _get_model_id(self) -> str:
        """Get the model ID from the LLM client configuration.

        Returns the primary model ID used for analysis metadata.
        """
        # Access the LLM client through the contradiction detector
        # (all detectors share the same LLM client)
        try:
            return self._contradiction_detector._llm_client.primary_model
        except AttributeError:
            return "unknown"
