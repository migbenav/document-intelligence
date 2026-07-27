"""Conclusions & Recommendations analyzer (C3.4).

Analyzes the document's structural coherence and produces observations about
organization quality. Each observation includes a category, a description in
the user's ui_language, and a structural suggestion in the document's own
language (since it references the document's terminology).

Requirements covered: Req 5 (criteria 1-7)
"""

import asyncio
import json
import logging

from app.analysis.llm_client import LLMClient
from app.analysis.on_demand.analyzer_response import AnalyzerResponse
from app.analysis.on_demand.models import ConclusionsResult
from app.analysis.on_demand.prompts.conclusions_v2 import PROMPT_TEMPLATE, PROMPT_VERSION
from app.analysis.on_demand.text_preparation import prepare_document_text
from app.models.document import IntermediateRepresentation

logger = logging.getLogger(__name__)

# Allowed observation categories per the v2 prompt and model definitions
ALLOWED_CATEGORIES = frozenset(
    {
        "purpose_mismatch",
        "misplaced_content",
        "title_mismatch",
        "sequence_issue",
        "duplication",
        "contradiction",
    }
)


class ConclusionsAnalyzer:
    """Produces structural observations about document organization via LLM.

    Unlike the other analyzers, Conclusions requires TWO language parameters:
    - response_language (ui_language): used for observation descriptions
    - document_language: used for structural suggestions, since they reference
      the document's own section names and terminology.
    """

    PROMPT_VERSION = PROMPT_VERSION

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    async def analyze(
        self,
        ir: IntermediateRepresentation,
        language: str,
        document_language: str,
        classification: str = "generic",
        model_override: str | None = None,
        auto_fallback: bool = True,
    ) -> AnalyzerResponse:
        """Run the Conclusions & Recommendations analysis on the full document.

        Args:
            ir: The document's IntermediateRepresentation with all chunks.
            language: The user's ui_language for descriptions (e.g., "es", "en").
            document_language: The document's own language for suggestions.
            classification: Document classification (e.g., "normative", "procedure").
                Defaults to "generic". Used in v2 prompts (tasks 5-8).
            model_override: Optional model identifier to override the default.
            auto_fallback: Whether to allow automatic fallback on transient errors.

        Returns:
            An AnalyzerResponse wrapping the ConclusionsResult with model metadata.

        Raises:
            asyncio.TimeoutError: If the LLM call exceeds the 30s timeout.
            ValueError: If the LLM response cannot be parsed or validated.
        """
        document_text = prepare_document_text(ir)

        prompt = PROMPT_TEMPLATE.format(
            classification=classification,
            response_language=language,
            document_language=document_language,
            document_text=document_text,
        )

        # Call LLM with 90s timeout (Decision 6 from design.md)
        llm_response = await asyncio.wait_for(
            self._llm_client.call(
                prompt,
                model_tier="primary",
                temperature=0.1,
                model_override=model_override,
                auto_fallback=auto_fallback,
            ),
            timeout=90.0,
        )

        # Parse response: strip ```json fences if present
        content = llm_response.content.strip()
        if content.startswith("```"):
            # Remove opening fence (```json or ```)
            first_newline = content.index("\n")
            content = content[first_newline + 1 :]
            # Remove closing fence
            if content.endswith("```"):
                content = content[: -len("```")]
            content = content.strip()

        # Parse JSON
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse LLM response as JSON for conclusions analysis",
                extra={"error": str(e), "raw_content": content[:500]},
            )
            raise ValueError(f"LLM returned invalid JSON: {e}") from e

        # Validate categories against allowed set
        if "observations" in data:
            for obs in data["observations"]:
                category = obs.get("category")
                if category and category not in ALLOWED_CATEGORIES:
                    logger.warning(
                        "Invalid category in conclusions observation, removing",
                        extra={"category": category},
                    )
                    obs["category"] = "purpose_mismatch"  # Default to purpose_mismatch for invalid

        # Validate with Pydantic model
        try:
            result = ConclusionsResult.model_validate(data)
        except Exception as e:
            logger.error(
                "Failed to validate conclusions result against schema",
                extra={"error": str(e), "data": str(data)[:500]},
            )
            raise ValueError(f"LLM response failed schema validation: {e}") from e

        logger.info(
            "Conclusions analysis completed",
            extra={
                "observation_count": len(result.observations),
                "model_id": llm_response.model_id,
            },
        )

        # Determine the requested model for fallback detection
        if model_override is not None and model_override != "default":
            requested_model = model_override
        else:
            requested_model = self._llm_client.primary_model

        # Detect whether fallback was used
        fallback_used = llm_response.model_id != requested_model

        return AnalyzerResponse(
            result=result,
            model_id=llm_response.model_id,
            prompt_version=PROMPT_VERSION,
            fallback_used=fallback_used,
        )
