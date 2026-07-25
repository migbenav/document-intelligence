"""Document type inference service.

Classifies documents using the light LLM model based on a sample of the IR
text content. Returns a TypeSuggestion with the inferred type and justification.

Requirements covered: 3.1, 3.2, 3.3, 3.5
"""

import json
import logging

from app.analysis.llm_client import LLMClient
from app.analysis.prompts import type_inference_v1
from app.models.document import IntermediateRepresentation
from app.models.knowledge_model import TypeSuggestion

logger = logging.getLogger(__name__)

_VALID_TYPES = {"prd", "technical_spec", "policy_process", "generic"}

# Maximum characters of IR text to send for type inference
_MAX_SAMPLE_CHARS = 2000


class TypeInferenceService:
    """Infers document type from the Intermediate Representation.

    Uses the light model tier (Groq) for fast, low-cost classification (Req 3.5).
    Returns a TypeSuggestion that is always populated with a justification (Req 3.2).
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    async def infer(self, ir: IntermediateRepresentation) -> TypeSuggestion:
        """Infer the document type from the IR content.

        Constructs a text sample from the first ~2000 characters of combined
        IR chunk text, calls the LLM via the light model tier, and parses the
        JSON response into a TypeSuggestion.

        When the LLM returns a valid type with sufficient confidence,
        document_type and suggested_type are both set to the detected type.
        When confidence is low or the response is unparseable, document_type
        is None and suggested_type is "generic" (Req 3.3).

        Args:
            ir: The Intermediate Representation of the document.

        Returns:
            TypeSuggestion with the inference result and justification.
        """
        # Build text sample from IR chunks (first ~2000 chars)
        ir_text_sample = self._build_text_sample(ir)

        # Construct the prompt using the versioned template
        prompt = type_inference_v1.build(ir_text_sample)

        # Call LLM with light model tier (Req 3.5)
        response = await self._llm_client.call(prompt, model_tier="light")

        # Parse and return the suggestion
        return self._parse_response(response.content)

    def _build_text_sample(self, ir: IntermediateRepresentation) -> str:
        """Build a text sample from the IR chunks, limited to ~2000 characters.

        Concatenates chunk text in order until the character limit is reached.
        Only includes document text content — no user metadata (Req 2.4).
        """
        parts: list[str] = []
        total_chars = 0

        for chunk in sorted(ir.chunks, key=lambda c: c.order):
            if total_chars >= _MAX_SAMPLE_CHARS:
                break

            remaining = _MAX_SAMPLE_CHARS - total_chars
            text = chunk.text[:remaining]
            parts.append(text)
            total_chars += len(text)

        return "\n".join(parts)

    def _parse_response(self, content: str) -> TypeSuggestion:
        """Parse the LLM response into a TypeSuggestion.

        On successful parse with a valid type, returns the detected type.
        On parse failure or invalid type, defaults gracefully to generic (Req 3.3).
        """
        try:
            data = json.loads(content.strip())
        except (json.JSONDecodeError, ValueError):
            logger.warning(
                "Type inference response is not valid JSON, defaulting to generic",
                extra={"raw_content": content[:200]},
            )
            return TypeSuggestion(
                document_type=None,
                suggested_type="generic",
                justification="Could not parse LLM response; defaulting to generic classification.",
            )

        # Extract document_type and justification from response
        document_type = data.get("document_type")
        justification = data.get("justification", "")

        # Validate the type is in our known set
        if document_type not in _VALID_TYPES:
            logger.warning(
                "Type inference returned unknown type, defaulting to generic",
                extra={"returned_type": document_type},
            )
            return TypeSuggestion(
                document_type=None,
                suggested_type="generic",
                justification=justification or "Unrecognized document type; defaulting to generic.",
            )

        # "generic" from the LLM means low confidence — treat as unset type (Req 3.3)
        if document_type == "generic":
            return TypeSuggestion(
                document_type=None,
                suggested_type="generic",
                justification=justification,
            )

        # Valid, confident classification
        return TypeSuggestion(
            document_type=document_type,
            suggested_type=document_type,
            justification=justification,
        )
