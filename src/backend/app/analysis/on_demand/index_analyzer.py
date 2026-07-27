"""IndexAnalyzer — Build Index analysis (C3.1).

Produces a hierarchical structure tree from the document's IR via a single
LLM call with the full document content. Each node in the tree identifies
its functional role and the question it answers in the document's knowledge
cascade.

Requirements covered: Req 2 (criteria 1-7)
"""

import asyncio
import json
import logging
import re

from app.analysis.llm_client import LLMClient, LLMResponse
from app.analysis.on_demand.models import IndexResult
from app.analysis.on_demand.prompts.build_index import PROMPT_TEMPLATE, PROMPT_VERSION
from app.analysis.on_demand.text_preparation import prepare_document_text
from app.models.document import IntermediateRepresentation

logger = logging.getLogger(__name__)

# Timeout for a single LLM call (Decision 6 from design.md)
_LLM_TIMEOUT_SECONDS = 90


class IndexAnalysisError(Exception):
    """Raised when the index analysis fails (parse error, validation error, etc.)."""

    pass


def _extract_json(text: str) -> str:
    """Extract JSON from LLM response, stripping markdown fences if present."""
    # Strip ```json ... ``` fences
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


class IndexAnalyzer:
    """Analyzer that builds a hierarchical structure tree from a document.

    Uses the full document IR in a single LLM call to produce an IndexResult
    containing a tree of StructureNodes with roles and cascade questions.
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
    ) -> IndexResult:
        """Analyze document structure and produce a hierarchical index.

        Args:
            ir: The document's intermediate representation with ordered chunks.
            language: The response language for the LLM output (e.g., "es", "en").
            model_override: Optional model identifier to override the default.
            auto_fallback: Whether to allow automatic fallback on transient errors.

        Returns:
            An IndexResult containing the structure tree.

        Raises:
            IndexAnalysisError: On JSON parse failure or validation error.
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
            "Starting Build Index analysis",
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

        # 4. Parse JSON response and validate as IndexResult
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
            raise IndexAnalysisError(
                f"LLM response is not valid JSON: {e}"
            ) from e

        try:
            result = IndexResult.model_validate(data)
        except Exception as e:
            logger.error(
                "Failed to validate LLM response against IndexResult schema",
                extra={
                    "document_id": ir.document_id,
                    "error": str(e),
                },
            )
            raise IndexAnalysisError(
                f"LLM response does not match IndexResult schema: {e}"
            ) from e

        logger.info(
            "Build Index analysis completed",
            extra={
                "document_id": ir.document_id,
                "model_id": response.model_id,
                "node_count": len(result.tree),
            },
        )

        # 5. Return validated IndexResult
        return result
