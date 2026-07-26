"""Unit tests for the ResponseParser module.

Covers: valid JSON parsing, document_id post-mapping, markdown code fence extraction,
parse failure error handling, corrective re-prompt construction, evidence max length
enforcement.

Requirements validated: 3.1, 3.2, 3.3, 3.5, 3.6
"""

import json

import pytest

from app.analysis.query.response_parser import ResponseParseError, ResponseParser


# --- Fixtures ---


@pytest.fixture
def parser() -> ResponseParser:
    """Create a ResponseParser instance."""
    return ResponseParser()


@pytest.fixture
def valid_llm_output() -> str:
    """A valid LLM output JSON string (without document_id or metadata)."""
    return json.dumps(
        {
            "answer": "The system uses a retry mechanism for transient failures.",
            "answerable": True,
            "source_refs": [
                {
                    "chunk_id": "chunk-001",
                    "page": 3,
                    "section": "## Reliability",
                    "evidence": "The service retries on transient network errors.",
                }
            ],
        }
    )


@pytest.fixture
def valid_cannot_answer_output() -> str:
    """A valid LLM output for a cannot-answer response."""
    return json.dumps(
        {
            "answer": "The available knowledge does not contain information about deployment.",
            "answerable": False,
            "source_refs": [],
        }
    )


# --- Test Cases ---


class TestResponseParserValidParsing:
    """Tests for successful JSON parsing and Pydantic validation (Req 3.1, 3.2)."""

    def test_parses_valid_json_output(
        self, parser: ResponseParser, valid_llm_output: str
    ):
        """Valid JSON with answer, answerable, source_refs is parsed successfully."""
        result = parser.parse(valid_llm_output, document_id="doc-123")

        assert result.answer == "The system uses a retry mechanism for transient failures."
        assert result.answerable is True
        assert len(result.source_refs) == 1

    def test_parses_cannot_answer_response(
        self, parser: ResponseParser, valid_cannot_answer_output: str
    ):
        """Cannot-answer response with empty source_refs is parsed successfully."""
        result = parser.parse(valid_cannot_answer_output, document_id="doc-123")

        assert result.answerable is False
        assert result.source_refs == []
        assert "does not contain" in result.answer

    def test_parses_multiple_source_refs(self, parser: ResponseParser):
        """Multiple source_refs are all parsed correctly."""
        output = json.dumps(
            {
                "answer": "The document describes actors and processes.",
                "answerable": True,
                "source_refs": [
                    {
                        "chunk_id": "chunk-001",
                        "page": 1,
                        "section": "## Actors",
                        "evidence": "The admin manages users.",
                    },
                    {
                        "chunk_id": "chunk-005",
                        "section": "## Processes",
                        "evidence": "The workflow starts with approval.",
                    },
                ],
            }
        )

        result = parser.parse(output, document_id="doc-456")

        assert len(result.source_refs) == 2
        assert result.source_refs[0].chunk_id == "chunk-001"
        assert result.source_refs[0].page == 1
        assert result.source_refs[1].chunk_id == "chunk-005"
        assert result.source_refs[1].page is None


class TestResponseParserDocumentIdMapping:
    """Tests for document_id post-mapping to all source_refs (Req 3.2)."""

    def test_sets_document_id_on_all_source_refs(
        self, parser: ResponseParser, valid_llm_output: str
    ):
        """document_id is set on each source_ref after parsing."""
        result = parser.parse(valid_llm_output, document_id="doc-abc")

        for ref in result.source_refs:
            assert ref.document_id == "doc-abc"

    def test_sets_document_id_on_multiple_refs(self, parser: ResponseParser):
        """document_id is set on all source_refs when there are multiple."""
        output = json.dumps(
            {
                "answer": "Multiple claims here.",
                "answerable": True,
                "source_refs": [
                    {"chunk_id": "c1", "evidence": "Evidence 1."},
                    {"chunk_id": "c2", "evidence": "Evidence 2."},
                    {"chunk_id": "c3", "evidence": "Evidence 3."},
                ],
            }
        )

        result = parser.parse(output, document_id="doc-xyz")

        assert all(ref.document_id == "doc-xyz" for ref in result.source_refs)

    def test_empty_source_refs_no_error(
        self, parser: ResponseParser, valid_cannot_answer_output: str
    ):
        """Parsing with empty source_refs and document_id succeeds without error."""
        result = parser.parse(valid_cannot_answer_output, document_id="doc-empty")

        assert result.source_refs == []


class TestResponseParserMarkdownCodeFences:
    """Tests for JSON extraction from markdown code fences (Req 3.3)."""

    def test_extracts_json_from_json_code_fence(self, parser: ResponseParser):
        """JSON wrapped in ```json ... ``` is extracted and parsed."""
        raw = '```json\n{"answer": "Hello", "answerable": true, "source_refs": []}\n```'

        result = parser.parse(raw, document_id="doc-1")

        assert result.answer == "Hello"
        assert result.answerable is True

    def test_extracts_json_from_plain_code_fence(self, parser: ResponseParser):
        """JSON wrapped in ``` ... ``` (without json tag) is extracted and parsed."""
        raw = '```\n{"answer": "World", "answerable": false, "source_refs": []}\n```'

        result = parser.parse(raw, document_id="doc-1")

        assert result.answer == "World"
        assert result.answerable is False

    def test_extracts_json_with_trailing_text_after_fence(self, parser: ResponseParser):
        """Trailing text after code fence is ignored."""
        raw = (
            '```json\n{"answer": "Found it", "answerable": true, "source_refs": '
            '[{"chunk_id": "c1", "evidence": "text"}]}\n```\n\n'
            "I hope this helps! Let me know if you have more questions."
        )

        result = parser.parse(raw, document_id="doc-2")

        assert result.answer == "Found it"
        assert len(result.source_refs) == 1

    def test_extracts_json_with_leading_text_before_brace(self, parser: ResponseParser):
        """Leading text before the JSON object is stripped."""
        raw = (
            "Here is the answer:\n"
            '{"answer": "The answer", "answerable": true, "source_refs": []}'
        )

        result = parser.parse(raw, document_id="doc-3")

        assert result.answer == "The answer"

    def test_extracts_json_with_trailing_text_after_brace(self, parser: ResponseParser):
        """Trailing text after JSON closing brace is ignored."""
        raw = (
            '{"answer": "Done", "answerable": true, "source_refs": []}'
            "\n\nNote: This is based on the provided context."
        )

        result = parser.parse(raw, document_id="doc-4")

        assert result.answer == "Done"


class TestResponseParserFailures:
    """Tests for parse failure raising ResponseParseError (Req 3.3, 3.6)."""

    def test_empty_output_raises_error(self, parser: ResponseParser):
        """Empty string raises ResponseParseError."""
        with pytest.raises(ResponseParseError, match="Empty LLM output"):
            parser.parse("", document_id="doc-1")

    def test_whitespace_only_raises_error(self, parser: ResponseParser):
        """Whitespace-only string raises ResponseParseError."""
        with pytest.raises(ResponseParseError, match="Empty LLM output"):
            parser.parse("   \n\t  ", document_id="doc-1")

    def test_invalid_json_raises_error(self, parser: ResponseParser):
        """Non-JSON text raises ResponseParseError."""
        with pytest.raises(ResponseParseError, match="Invalid JSON"):
            parser.parse("This is not JSON at all", document_id="doc-1")

    def test_json_array_instead_of_object_raises_error(self, parser: ResponseParser):
        """JSON array (not object) raises ResponseParseError."""
        with pytest.raises(ResponseParseError, match="not a JSON object"):
            parser.parse("[1, 2, 3]", document_id="doc-1")

    def test_missing_answer_field_raises_error(self, parser: ResponseParser):
        """Missing 'answer' field raises ResponseParseError."""
        raw = json.dumps({"answerable": True, "source_refs": []})

        with pytest.raises(ResponseParseError, match="does not conform"):
            parser.parse(raw, document_id="doc-1")

    def test_missing_answerable_field_raises_error(self, parser: ResponseParser):
        """Missing 'answerable' field raises ResponseParseError."""
        raw = json.dumps({"answer": "Hello", "source_refs": []})

        with pytest.raises(ResponseParseError, match="does not conform"):
            parser.parse(raw, document_id="doc-1")

    def test_error_preserves_raw_output(self, parser: ResponseParser):
        """ResponseParseError includes the raw output for debugging."""
        bad_output = "totally not json {{"
        with pytest.raises(ResponseParseError) as exc_info:
            parser.parse(bad_output, document_id="doc-1")

        assert exc_info.value.raw_output == bad_output


class TestResponseParserEvidenceConstraints:
    """Tests for evidence max 500 char enforcement (Req 3.5)."""

    def test_evidence_within_500_chars_succeeds(self, parser: ResponseParser):
        """Evidence text of exactly 500 chars is accepted."""
        evidence = "A" * 500
        output = json.dumps(
            {
                "answer": "The answer.",
                "answerable": True,
                "source_refs": [
                    {"chunk_id": "c1", "evidence": evidence}
                ],
            }
        )

        result = parser.parse(output, document_id="doc-1")

        assert len(result.source_refs[0].evidence) == 500

    def test_evidence_exceeding_500_chars_raises_error(self, parser: ResponseParser):
        """Evidence text exceeding 500 chars causes validation failure."""
        evidence = "A" * 501
        output = json.dumps(
            {
                "answer": "The answer.",
                "answerable": True,
                "source_refs": [
                    {"chunk_id": "c1", "evidence": evidence}
                ],
            }
        )

        with pytest.raises(ResponseParseError, match="does not conform"):
            parser.parse(output, document_id="doc-1")


class TestResponseParserCorrectiveReprompt:
    """Tests for corrective re-prompt construction (Req 3.3)."""

    def test_reprompt_includes_original_prompt(self, parser: ResponseParser):
        """Corrective re-prompt includes the original prompt."""
        reprompt = parser.build_corrective_reprompt(
            original_prompt="Answer the question based on context.",
            raw_output='{"bad": "json"}',
            error="Missing 'answer' field.",
        )

        assert "Answer the question based on context." in reprompt

    def test_reprompt_includes_invalid_output(self, parser: ResponseParser):
        """Corrective re-prompt includes the invalid output."""
        raw_output = '{"bad": "json"}'
        reprompt = parser.build_corrective_reprompt(
            original_prompt="Original prompt here.",
            raw_output=raw_output,
            error="Missing field.",
        )

        assert raw_output in reprompt

    def test_reprompt_includes_error_details(self, parser: ResponseParser):
        """Corrective re-prompt includes the specific error description."""
        error_msg = "Missing required field 'answerable'"
        reprompt = parser.build_corrective_reprompt(
            original_prompt="Prompt.",
            raw_output="{}",
            error=error_msg,
        )

        assert error_msg in reprompt

    def test_reprompt_instructs_valid_json(self, parser: ResponseParser):
        """Corrective re-prompt instructs the LLM to produce valid JSON."""
        reprompt = parser.build_corrective_reprompt(
            original_prompt="Prompt.",
            raw_output="bad",
            error="Not JSON.",
        )

        assert "valid JSON" in reprompt

    def test_reprompt_mentions_previous_was_invalid(self, parser: ResponseParser):
        """Corrective re-prompt explicitly states previous response was invalid."""
        reprompt = parser.build_corrective_reprompt(
            original_prompt="Prompt.",
            raw_output="{}",
            error="Error.",
        )

        assert "invalid" in reprompt.lower()


class TestResponseParserEdgeCases:
    """Tests for edge cases in parsing."""

    def test_handles_nested_json_in_evidence(self, parser: ResponseParser):
        """JSON content within evidence strings doesn't break extraction."""
        output = json.dumps(
            {
                "answer": "The config uses JSON format.",
                "answerable": True,
                "source_refs": [
                    {
                        "chunk_id": "c1",
                        "evidence": 'The config file contains {"key": "value"} entries.',
                    }
                ],
            }
        )

        result = parser.parse(output, document_id="doc-1")

        assert '{"key": "value"}' in result.source_refs[0].evidence

    def test_handles_source_ref_with_optional_fields_missing(
        self, parser: ResponseParser
    ):
        """source_ref with only required fields (chunk_id, evidence) is valid."""
        output = json.dumps(
            {
                "answer": "Answer text.",
                "answerable": True,
                "source_refs": [
                    {"chunk_id": "chunk-001", "evidence": "Some evidence."}
                ],
            }
        )

        result = parser.parse(output, document_id="doc-1")

        ref = result.source_refs[0]
        assert ref.chunk_id == "chunk-001"
        assert ref.page is None
        assert ref.section is None
        assert ref.evidence_verified is False  # Default

    def test_placeholder_metadata_is_injected(
        self, parser: ResponseParser, valid_llm_output: str
    ):
        """When LLM output has no metadata, placeholder metadata is injected."""
        result = parser.parse(valid_llm_output, document_id="doc-1")

        # Metadata should exist (placeholder injected)
        assert result.metadata is not None
        assert result.metadata.prompt_version == "placeholder"
