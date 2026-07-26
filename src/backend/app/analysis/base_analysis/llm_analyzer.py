"""LLM-based analyzer for document summary and classification.

Sends a single prompt to the light model with a 10-second timeout.
Returns None on any failure (timeout, LLM error, invalid JSON, missing fields)
without raising exceptions. All failures are logged.

Requirements covered: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
"""

import asyncio
import json
import logging
from dataclasses import dataclass

from app.analysis.llm_client import LLMClient, LLMAuthenticationError, LLMTransientError
from app.models.document import ContentChunkModel
from app.models.document_card import DocumentClassification, OrganizationType

from .prompts import PROMPT_TEMPLATE, PROMPT_VERSION

logger = logging.getLogger(__name__)

# Timeout for the LLM call (seconds) — ADR-007 specifies 10s max
LLM_TIMEOUT_SECONDS = 10

# Maximum number of chunks to include in the text sample
MAX_CHUNKS = 10

# Maximum character length for the text sample
MAX_TEXT_SAMPLE_CHARS = 2000

# ISO language code to full language name mapping
LANGUAGE_MAP: dict[str, str] = {
    "es": "Spanish",
    "en": "English",
}


@dataclass
class LLMAnalysisResult:
    """Result of a successful LLM analysis call."""

    summary: str
    classification: DocumentClassification
    model_id: str
    prompt_version: str


class LLMAnalyzer:
    """Single LLM call for summary + classification. Returns None on any failure.

    Data minimization (Req 3.7): the prompt contains ONLY title, organization_type,
    and a text sample. No user identity, session history, account metadata, or
    document_id is included.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """Initialize with an LLMClient instance.

        Args:
            llm_client: The LLM client used to communicate with the model.
        """
        self._llm_client = llm_client

    async def analyze(
        self,
        title: str,
        chunks: list[ContentChunkModel],
        organization_type: OrganizationType,
        language: str = "es",
        model_override: str | None = None,
        auto_fallback: bool = True,
    ) -> LLMAnalysisResult | None:
        """Call the light model to produce a summary and classification.

        Builds a prompt with title, organization_type, and a text sample from
        the first 10 chunks (max 2000 chars). Applies a 10-second timeout.

        Returns None on any failure: timeout, LLM error, invalid JSON, or
        missing/invalid fields. Logs failures without raising exceptions.

        Args:
            title: The document title (extracted during local processing).
            chunks: The document's content chunks from the IR.
            organization_type: The detected organization type.
            language: ISO language code ('es' or 'en'). Defaults to 'es'.
            model_override: If provided, override the default model for this call.
            auto_fallback: Whether to enable automatic fallback on transient errors.

        Returns:
            LLMAnalysisResult on success, None on any failure.
        """
        try:
            prompt = self._build_prompt(title, chunks, organization_type, language)
            response = await asyncio.wait_for(
                self._llm_client.call(
                    prompt,
                    model_tier="light",
                    temperature=0.1,
                    model_override=model_override,
                    auto_fallback=auto_fallback,
                ),
                timeout=LLM_TIMEOUT_SECONDS,
            )
            return self._parse_response(response.content, response.model_id)

        except asyncio.TimeoutError:
            logger.warning(
                "LLM call timed out after %d seconds for document titled '%s'",
                LLM_TIMEOUT_SECONDS,
                title,
            )
            return None

        except LLMTransientError as e:
            logger.warning(
                "LLM transient error during base analysis for document titled '%s': %s",
                title,
                str(e),
            )
            return None

        except LLMAuthenticationError as e:
            logger.error(
                "LLM authentication error during base analysis: %s", str(e)
            )
            return None

        except Exception as e:
            logger.error(
                "Unexpected error during LLM analysis for document titled '%s': %s",
                title,
                str(e),
                exc_info=True,
            )
            return None

    def _build_prompt(
        self,
        title: str,
        chunks: list[ContentChunkModel],
        organization_type: OrganizationType,
        language: str = "es",
    ) -> str:
        """Build the prompt from title, organization type, and text sample.

        Takes the first 10 chunks concatenated, truncated to 2000 characters max.
        Only title, organization_type, and text are included (Req 3.7 data minimization).

        Args:
            title: The document title.
            chunks: The document's content chunks.
            organization_type: The detected organization type.
            language: ISO language code ('es' or 'en'). Defaults to 'es'.

        Returns:
            The formatted prompt string.
        """
        text_sample = self._build_text_sample(chunks)
        response_language = LANGUAGE_MAP.get(language, "Spanish")
        return PROMPT_TEMPLATE.format(
            response_language=response_language,
            title=title,
            organization_type=organization_type.value,
            text_sample=text_sample,
        )

    def _build_text_sample(self, chunks: list[ContentChunkModel]) -> str:
        """Concatenate the first 10 chunks, truncated to 2000 characters.

        Args:
            chunks: The document's content chunks.

        Returns:
            The text sample string (max 2000 chars).
        """
        selected_chunks = chunks[:MAX_CHUNKS]
        combined = "\n".join(chunk.text for chunk in selected_chunks)
        return combined[:MAX_TEXT_SAMPLE_CHARS]

    def _parse_response(self, content: str, model_id: str) -> LLMAnalysisResult | None:
        """Parse the LLM response as JSON and validate required fields.

        Expects a JSON object with "summary" (string) and "classification"
        (one of the valid DocumentClassification values).

        Returns None if JSON is invalid or fields are missing/invalid.

        Args:
            content: The raw text response from the LLM.
            model_id: The model identifier that produced the response.

        Returns:
            LLMAnalysisResult on success, None on parse/validation failure.
        """
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("LLM response is not valid JSON: %s", str(e))
            return None

        if not isinstance(data, dict):
            logger.warning("LLM response is not a JSON object")
            return None

        summary = data.get("summary")
        classification_value = data.get("classification")

        if not summary or not isinstance(summary, str):
            logger.warning("LLM response missing or invalid 'summary' field")
            return None

        if not classification_value or not isinstance(classification_value, str):
            logger.warning("LLM response missing or invalid 'classification' field")
            return None

        # Validate classification against the enum
        try:
            classification = DocumentClassification(classification_value)
        except ValueError:
            logger.warning(
                "LLM response has invalid classification value: '%s'",
                classification_value,
            )
            return None

        return LLMAnalysisResult(
            summary=summary,
            classification=classification,
            model_id=model_id,
            prompt_version=PROMPT_VERSION,
        )
