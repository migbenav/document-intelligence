"""QueryService orchestrator for the natural language query pipeline.

Coordinates context construction, LLM call, response parsing, and evidence
verification to produce grounded answers to natural language questions about
a document's Knowledge Model.

Requirements covered: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 7.3, 7.4, 7.5
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.analysis.llm_client import LLMClient
from app.analysis.prompts import query_answering_v1
from app.analysis.query.context_builder import ContextBuilder
from app.analysis.query.evidence_verifier import QueryEvidenceVerifier
from app.analysis.query.response_parser import ResponseParseError, ResponseParser
from app.models.document import IntermediateRepresentation
from app.models.knowledge_model import KnowledgeModel
from app.models.query import QueryMetadata, QueryResponse

logger = logging.getLogger(__name__)

# ISO language code to full language name mapping
LANGUAGE_MAP: dict[str, str] = {
    "es": "Spanish",
    "en": "English",
}

# Total timeout for the entire answer pipeline (seconds)
_PIPELINE_TIMEOUT_SECONDS = 30


class QueryError(Exception):
    """Raised when the query pipeline fails (LLM error, timeout, or parse failure after retry)."""

    pass


class QueryService:
    """Orchestrates the complete natural language query pipeline.

    Each call to `answer()` is independent — no state is maintained between
    calls. The service coordinates:
    1. Context construction (selecting relevant KM elements).
    2. Prompt building via query_answering_v1.
    3. LLM call (primary tier, temperature ≤ 0.1).
    4. Response parsing (with one retry on failure).
    5. Evidence verification against the IR.
    6. Metadata attachment.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        context_builder: ContextBuilder,
        response_parser: ResponseParser,
        evidence_verifier: QueryEvidenceVerifier,
        temperature: float = 0.1,
    ) -> None:
        """Initialize the QueryService.

        Args:
            llm_client: LLM client for answer generation calls.
            context_builder: Builds query context from the Knowledge Model.
            response_parser: Parses and validates LLM output.
            evidence_verifier: Verifies evidence spans against the IR.
            temperature: Temperature for LLM calls (default 0.1, must be ≤ 0.1
                for reproducibility unless explicitly overridden).
        """
        self._llm_client = llm_client
        self._context_builder = context_builder
        self._response_parser = response_parser
        self._evidence_verifier = evidence_verifier
        self._temperature = temperature

    async def answer(
        self,
        document_id: str,
        question: str,
        knowledge_model: KnowledgeModel,
        ir: IntermediateRepresentation,
        language: str = "es",
        model_override: str | None = None,
        auto_fallback: bool = True,
    ) -> QueryResponse:
        """Process a natural language query and return a grounded answer.

        Pipeline:
        1. Build context (select relevant KM elements).
        2. If context is empty → return cannot-answer response.
        3. Construct prompt via query_answering_v1.build().
        4. Call LLM (primary tier, temperature ≤ 0.1).
        5. Parse response (with one retry on failure via corrective re-prompt).
        6. Verify evidence against IR.
        7. Compute all_evidence_unverified flag.
        8. Attach metadata.

        Args:
            document_id: The document ID for source_ref mapping.
            question: The user's natural language question.
            knowledge_model: The completed Knowledge Model for the document.
            ir: The Intermediate Representation for evidence verification.
            language: ISO language code ('es' or 'en') for LLM response language.
                Defaults to 'es'.
            model_override: If provided, override the default model selection.
            auto_fallback: Whether to allow automatic fallback to alternate model
                on transient errors. Defaults to True.

        Returns:
            QueryResponse with the answer, source_refs, and metadata.

        Raises:
            QueryError: On LLM failure/timeout or parse failure after retry.
        """
        try:
            return await asyncio.wait_for(
                self._execute_pipeline(
                    document_id, question, knowledge_model, ir, language,
                    model_override=model_override, auto_fallback=auto_fallback,
                ),
                timeout=_PIPELINE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            raise QueryError(
                f"Query processing timed out after {_PIPELINE_TIMEOUT_SECONDS} seconds."
            )

    async def _execute_pipeline(
        self,
        document_id: str,
        question: str,
        knowledge_model: KnowledgeModel,
        ir: IntermediateRepresentation,
        language: str = "es",
        model_override: str | None = None,
        auto_fallback: bool = True,
    ) -> QueryResponse:
        """Execute the query pipeline without timeout wrapping.

        This is the internal implementation separated to allow asyncio.wait_for
        to wrap it with a timeout.
        """
        # Step 1: Build context
        context = await self._context_builder.build_context(
            question=question,
            knowledge_model=knowledge_model,
            ir=ir,
            context_window_tokens=128000,  # Default context window size
        )

        # Step 2: Check empty context → cannot-answer response
        if context is None:
            return self._build_cannot_answer_response(document_id)

        # Step 3: Build prompt with language instruction
        context_elements = [
            {
                "type": elem.type,
                "name": elem.name,
                "content": elem.content,
                "evidence": elem.evidence,
                "verified": elem.verified,
            }
            for elem in context.elements
        ]
        relations = [
            {
                "source_id": rel.source_id,
                "target_id": rel.target_id,
                "type": rel.type,
            }
            for rel in context.relations
        ]
        base_prompt = query_answering_v1.build(context_elements, relations, question)

        # Prepend language instruction to the prompt
        response_language = LANGUAGE_MAP.get(language, "Spanish")
        prompt = f"Respond in {response_language}.\n{base_prompt}"

        # Step 4: Call LLM (primary tier)
        try:
            llm_response = await self._llm_client.call(
                prompt, model_tier="primary", temperature=self._temperature,
                model_override=model_override, auto_fallback=auto_fallback,
            )
        except Exception as e:
            raise QueryError(f"LLM call failed: {e}") from e

        # Step 5: Parse response (with one retry on failure)
        response = await self._parse_with_retry(
            llm_response.content, document_id, prompt,
            model_override=model_override, auto_fallback=auto_fallback,
        )

        # Step 6: Verify evidence
        if response.source_refs:
            self._evidence_verifier.verify(response.source_refs, ir)

        # Step 7: Compute all_evidence_unverified flag
        if response.source_refs:
            all_unverified = all(
                not ref.evidence_verified for ref in response.source_refs
            )
            response.all_evidence_unverified = all_unverified

        # Step 8: Attach metadata
        metadata = QueryMetadata(
            prompt_version=query_answering_v1.VERSION,
            model_id=llm_response.model_id,
            temperature=self._temperature,
            timestamp=datetime.now(timezone.utc),
        )
        response.metadata = metadata

        return response

    async def _parse_with_retry(
        self, raw_output: str, document_id: str, original_prompt: str,
        model_override: str | None = None, auto_fallback: bool = True,
    ) -> QueryResponse:
        """Parse LLM output with one retry on failure via corrective re-prompt.

        Args:
            raw_output: The raw LLM output from the first call.
            document_id: Document ID for source_ref mapping.
            original_prompt: The original prompt for corrective re-prompt construction.
            model_override: If provided, override the default model selection.
            auto_fallback: Whether to allow automatic fallback on transient errors.

        Returns:
            Validated QueryResponse.

        Raises:
            QueryError: If both parse attempts fail.
        """
        # First attempt
        first_error_message: str | None = None
        try:
            return self._response_parser.parse(raw_output, document_id)
        except ResponseParseError as first_error:
            first_error_message = str(first_error)
            logger.warning(
                "First parse attempt failed, retrying with corrective re-prompt",
                extra={"error": first_error_message},
            )

        # Build corrective re-prompt and retry
        corrective_prompt = self._response_parser.build_corrective_reprompt(
            original_prompt, raw_output, first_error_message
        )

        try:
            retry_response = await self._llm_client.call(
                corrective_prompt, model_tier="primary", temperature=self._temperature,
                model_override=model_override, auto_fallback=auto_fallback,
            )
        except Exception as e:
            raise QueryError(
                f"LLM retry call failed after parse error: {e}"
            ) from e

        # Second parse attempt
        try:
            return self._response_parser.parse(retry_response.content, document_id)
        except ResponseParseError as second_error:
            raise QueryError(
                f"Response parsing failed after retry: {second_error}"
            ) from second_error

    def _build_cannot_answer_response(self, document_id: str) -> QueryResponse:
        """Build a cannot-answer response when context is empty.

        Returns a QueryResponse with answerable=False, empty source_refs,
        and metadata still attached.
        """
        return QueryResponse(
            answer=(
                "The available knowledge does not contain information relevant to "
                "this question. The Knowledge Model does not have elements that "
                "match the question's subject matter."
            ),
            answerable=False,
            source_refs=[],
            all_evidence_unverified=False,
            metadata=QueryMetadata(
                prompt_version=query_answering_v1.VERSION,
                model_id="none",
                temperature=self._temperature,
                timestamp=datetime.now(timezone.utc),
            ),
        )
