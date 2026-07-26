"""Response parser for LLM query output.

Parses raw LLM JSON output into a validated QueryResponse, handling common
LLM output issues (markdown code fences, trailing text). Provides corrective
re-prompt construction for retry on parse failure.

Requirements: 3.1, 3.2, 3.3, 3.5, 3.6
"""

import json
import re
from datetime import datetime, timezone

from pydantic import ValidationError

from app.models.query import QueryMetadata, QueryResponse, QuerySourceRef


class ResponseParseError(Exception):
    """Raised when LLM output cannot be parsed into a valid QueryResponse."""

    def __init__(self, message: str, raw_output: str | None = None):
        super().__init__(message)
        self.raw_output = raw_output


class ResponseParser:
    """Parses LLM output into QueryResponse with validation.

    Handles common LLM output issues:
    - JSON wrapped in markdown code fences (```json ... ```)
    - Trailing text after the JSON object
    - Missing or extra fields

    Raises ResponseParseError on validation failure.

    Note: The LLM output contains answer, answerable, and source_refs fields
    but does NOT include metadata or document_id on source_refs. The parser
    injects document_id on each source_ref and provides placeholder metadata
    that the QueryService will replace with actual values.
    """

    def parse(self, raw_output: str, document_id: str) -> QueryResponse:
        """Parse raw LLM JSON output into a validated QueryResponse.

        The document_id parameter is set on each source_ref after parsing
        (the LLM output does not contain document_id — only chunk_ids).

        A placeholder metadata is injected if not present in the LLM output,
        since metadata is attached by the QueryService after parsing.

        Args:
            raw_output: Raw string output from the LLM.
            document_id: Document ID to set on each source_ref.

        Returns:
            Validated QueryResponse with document_id set on all source_refs.

        Raises:
            ResponseParseError: If the output cannot be parsed or validated.
        """
        # Step 1: Extract JSON from raw output
        json_str = self._extract_json(raw_output)

        # Step 2: Parse JSON string
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ResponseParseError(
                f"Invalid JSON in LLM output: {e}",
                raw_output=raw_output,
            )

        if not isinstance(data, dict):
            raise ResponseParseError(
                "LLM output is not a JSON object.",
                raw_output=raw_output,
            )

        # Step 3: Set document_id on each source_ref before validation
        if "source_refs" in data and isinstance(data["source_refs"], list):
            for ref in data["source_refs"]:
                if isinstance(ref, dict):
                    ref["document_id"] = document_id

        # Step 4: Inject placeholder metadata if not present
        # The QueryService will overwrite this with actual values after parsing.
        if "metadata" not in data:
            data["metadata"] = {
                "prompt_version": "placeholder",
                "model_id": "placeholder",
                "temperature": 0.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        # Step 5: Validate against Pydantic schema
        try:
            response = QueryResponse(**data)
        except ValidationError as e:
            error_details = str(e)
            raise ResponseParseError(
                f"LLM output does not conform to QueryResponse schema: {error_details}",
                raw_output=raw_output,
            )

        return response

    def build_corrective_reprompt(
        self, original_prompt: str, raw_output: str, error: str
    ) -> str:
        """Build a corrective re-prompt for retry after parse failure.

        Includes the original prompt, the invalid output, and the specific
        error so the LLM can correct its response.

        Args:
            original_prompt: The original prompt sent to the LLM.
            raw_output: The invalid output from the first attempt.
            error: Description of the parsing/validation error.

        Returns:
            A corrective re-prompt string for the retry attempt.
        """
        return (
            f"{original_prompt}\n\n"
            f"---\n"
            f"Your previous response was invalid and could not be parsed.\n\n"
            f"Previous output:\n"
            f"```\n{raw_output}\n```\n\n"
            f"Error: {error}\n\n"
            f"Please produce a corrected response that is valid JSON conforming "
            f"to the required schema. Output ONLY the JSON object, with no "
            f"additional text before or after it."
        )

    def _extract_json(self, raw_output: str) -> str:
        """Extract JSON from raw LLM output.

        Handles:
        - JSON wrapped in markdown code fences (```json ... ``` or ``` ... ```)
        - Trailing text after the closing brace of the JSON object
        - Plain JSON output

        Args:
            raw_output: Raw LLM output string.

        Returns:
            Extracted JSON string.

        Raises:
            ResponseParseError: If no JSON can be extracted.
        """
        if not raw_output or not raw_output.strip():
            raise ResponseParseError(
                "Empty LLM output — no JSON to parse.",
                raw_output=raw_output,
            )

        text = raw_output.strip()

        # Try to extract from markdown code fences
        code_fence_pattern = re.compile(
            r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL
        )
        match = code_fence_pattern.search(text)
        if match:
            return match.group(1).strip()

        # Try to find a JSON object by locating the first { and its matching }
        json_str = self._extract_json_object(text)
        if json_str:
            return json_str

        # Last resort: return the raw text and let JSON parsing handle the error
        return text

    def _extract_json_object(self, text: str) -> str | None:
        """Extract a JSON object from text by finding matching braces.

        Finds the first '{' and its matching '}', handling nested braces.
        This strips trailing text after the JSON object.

        Args:
            text: Text potentially containing a JSON object.

        Returns:
            The extracted JSON string, or None if no valid object found.
        """
        start = text.find("{")
        if start == -1:
            return None

        depth = 0
        in_string = False
        escape_next = False

        for i in range(start, len(text)):
            char = text[i]

            if escape_next:
                escape_next = False
                continue

            if char == "\\":
                if in_string:
                    escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

        return None
