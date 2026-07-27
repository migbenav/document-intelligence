"""QuestionsAnalyzer — Questions Answered analysis (C3.3).

Produces a cascade of questions that the document addresses, organized into
document-level (3-5 broad questions) and section-level (1-2 per major section)
via a single LLM call with the full document content.

Requirements covered: Req 4 (criteria 1-7)
"""

import asyncio
import json
import logging
import re

from app.analysis.llm_client import LLMClient, LLMResponse
from app.analysis.on_demand.models import QuestionsResult
from app.analysis.on_demand.prompts.questions_answered import (
    PROMPT_TEMPLATE,
    PROMPT_VERSION,
)
from app.analysis.on_demand.text_preparation import prepare_document_text
from app.models.document import IntermediateRepresentation

logger = logging.getLogger(__name__)

# Timeout for a single LLM call (Decision 6 from design.md)
_LLM_TIMEOUT_SECONDS = 30


class QuestionsAnalysisError(Exception):
    """Raised when the questions analysis fails (parse error, validation error, etc.)."""

    pass


def _extract_json(text: str) -> str:
    """Extract JSON from LLM response, stripping markdown fences if present."""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


class QuestionsAnalyzer:
    """Analyzer that generates a cascade of questions the document addresses.

    Uses the full document IR in a single LLM call to produce a QuestionsResult
    containing document-level and section-level questions with source references.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    @property
    def prompt_version(self) -> str:
        """Return the prompt version used by this analyzer."""
        return PROMPT_VERSION

    async def analyze(
        self,
        ir: IntermediateRepresentation,
        language: str,
        model_override: str | None = None,
        auto_fallback: bool = True,
    ) -> QuestionsResult:
        """Analyze document and produce a cascade of answered questions.

        Args:
            ir: The document's intermediate representation with ordered chunks.
            language: The response language for the LLM output (e.g., "es", "en").
            model_override: Optional model identifier to override the default.
            auto_fallback: Whether to allow automatic fallback on transient errors.

        Returns:
            A QuestionsResult containing document_questions and section_questions.

        Raises:
            QuestionsAnalysisError: On JSON parse failure or validation error.
            asyncio.TimeoutError: If the LLM call exceeds 30 seconds.
            LLMTransientError: If the LLM call fails with a transient error.
            LLMAuthenticationError: If the LLM credentials are invalid.
        """
        # 1. Build full document text from IR chunks with section markers
        document_text = prepare_document_text(ir)

        # 2. Format the prompt with response language and document content
        prompt = PROMPT_TEMPLATE.format(
            response_language=language,
            document_text=document_text,
        )

        # 3. Call LLM with 30s timeout
        logger.info(
            "Starting Questions Answered analysis",
            extra={"document_id": ir.document_id, "language": language},
        )

        response: LLMResponse = await asyncio.wait_for(
            self._llm_client.call(
                prompt,
                model_tier="primary",
                temperature=0.1,
                model_override=model_override,
                auto_fallback=auto_fallback,
            ),
            timeout=_LLM_TIMEOUT_SECONDS,
        )

        # 4. Parse JSON response
        raw_json = _extract_json(response.content)

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse LLM response as JSON",
                extra={
                    "document_id": ir.document_id,
                    "error": str(e),
                    "raw_content_preview": response.content[:200],
                },
            )
            raise QuestionsAnalysisError(
                f"LLM response is not valid JSON: {e}"
            ) from e

        # 5. Validate cascade structure: document_questions and section_questions levels
        self._validate_cascade_levels(data, ir.document_id)

        # 6. Validate as QuestionsResult using Pydantic model_validate
        try:
            result = QuestionsResult.model_validate(data)
        except Exception as e:
            logger.error(
                "Failed to validate LLM response against QuestionsResult schema",
                extra={
                    "document_id": ir.document_id,
                    "error": str(e),
                },
            )
            raise QuestionsAnalysisError(
                f"LLM response does not match QuestionsResult schema: {e}"
            ) from e

        logger.info(
            "Questions Answered analysis completed",
            extra={
                "document_id": ir.document_id,
                "model_id": response.model_id,
                "document_questions_count": len(result.document_questions),
                "section_questions_count": len(result.section_questions),
            },
        )

        # 7. Return validated QuestionsResult
        return result

    def _validate_cascade_levels(self, data: dict, document_id: str) -> None:
        """Validate that cascade structure has correct levels.

        Ensures document_questions all have level="document" and
        section_questions all have level="section".

        Raises:
            QuestionsAnalysisError: If any question has an incorrect level.
        """
        document_questions = data.get("document_questions", [])
        for i, q in enumerate(document_questions):
            if isinstance(q, dict) and q.get("level") != "document":
                logger.error(
                    "Document question has incorrect level",
                    extra={
                        "document_id": document_id,
                        "index": i,
                        "actual_level": q.get("level"),
                    },
                )
                raise QuestionsAnalysisError(
                    f"document_questions[{i}] has level='{q.get('level')}', "
                    f"expected 'document'"
                )

        section_questions = data.get("section_questions", [])
        for i, q in enumerate(section_questions):
            if isinstance(q, dict) and q.get("level") != "section":
                logger.error(
                    "Section question has incorrect level",
                    extra={
                        "document_id": document_id,
                        "index": i,
                        "actual_level": q.get("level"),
                    },
                )
                raise QuestionsAnalysisError(
                    f"section_questions[{i}] has level='{q.get('level')}', "
                    f"expected 'section'"
                )
