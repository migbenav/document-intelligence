"""Unit tests for completeness evaluation prompt template.

Verifies:
- Version constant is accessible and correct
- Schema inclusion instruction is present in the prompt
- Partial assessment instructions are clear
- No user metadata or session info included
- Output schema instructions present

Requirements validated: 3.1, 3.5, 9.2, 10.4, 10.7, 10.8
"""

import json

import pytest

from app.analysis.prompts import completeness_evaluation_v1


class TestCompletenessEvaluationV1Version:
    """Tests for the VERSION constant (Req 10.8)."""

    def test_version_constant_exists(self):
        assert hasattr(completeness_evaluation_v1, "VERSION")

    def test_version_is_string(self):
        assert isinstance(completeness_evaluation_v1.VERSION, str)

    def test_version_value(self):
        assert completeness_evaluation_v1.VERSION == "completeness-v1"


class TestCompletenessEvaluationV1SchemaInclusion:
    """Tests that the prompt includes the document type schema (Req 10.4)."""

    @pytest.fixture
    def sample_schema_json(self) -> str:
        schema = [
            {
                "name": "propósito",
                "description": "Document purpose and product goal",
                "importance": "high",
            },
            {
                "name": "requisitos funcionales",
                "description": "Functional requirements",
                "importance": "high",
            },
        ]
        return json.dumps(schema, ensure_ascii=False)

    @pytest.fixture
    def sample_elements_json(self) -> str:
        elements = [
            {
                "expected_element_name": "propósito",
                "matched_km_elements": [
                    {
                        "id": "elem-001",
                        "type": "proposito",
                        "name": "Product purpose",
                        "content": "This system manages documents.",
                    }
                ],
            }
        ]
        return json.dumps(elements, ensure_ascii=False)

    def test_schema_json_included_in_prompt(
        self, sample_elements_json: str, sample_schema_json: str
    ):
        """The document type schema must be included in the prompt (Req 10.4)."""
        result = completeness_evaluation_v1.build(sample_elements_json, sample_schema_json)
        assert sample_schema_json in result

    def test_schema_section_header_present(
        self, sample_elements_json: str, sample_schema_json: str
    ):
        """The prompt clearly delineates the schema section."""
        result = completeness_evaluation_v1.build(sample_elements_json, sample_schema_json)
        assert "DOCUMENT TYPE SCHEMA" in result

    def test_elements_json_included_in_prompt(
        self, sample_elements_json: str, sample_schema_json: str
    ):
        """The matched KM elements must be included in the prompt."""
        result = completeness_evaluation_v1.build(sample_elements_json, sample_schema_json)
        assert sample_elements_json in result

    def test_elements_section_header_present(
        self, sample_elements_json: str, sample_schema_json: str
    ):
        """The prompt clearly delineates the elements section."""
        result = completeness_evaluation_v1.build(sample_elements_json, sample_schema_json)
        assert "MATCHED KNOWLEDGE MODEL ELEMENTS" in result


class TestCompletenessEvaluationV1PartialAssessment:
    """Tests that the prompt provides clear partial assessment instructions (Req 3.1, 3.5)."""

    @pytest.fixture
    def prompt(self) -> str:
        return completeness_evaluation_v1.build(
            elements_json="[]",
            schema_json="[]",
        )

    def test_partial_classification_defined(self, prompt: str):
        """Prompt defines the 'partial' classification clearly."""
        assert "partial" in prompt.lower()

    def test_full_classification_defined(self, prompt: str):
        """Prompt defines the 'full' classification clearly."""
        assert "full" in prompt.lower()

    def test_coverage_criteria_mentioned(self, prompt: str):
        """Prompt specifies the coverage threshold for partial classification (Req 3.5)."""
        # Req 3.5: partial = covers fewer than half of the sub-aspects
        assert "fewer than half" in prompt.lower()

    def test_sub_aspects_mentioned(self, prompt: str):
        """Prompt references sub-aspects of the schema definition."""
        assert "sub-aspects" in prompt.lower()

    def test_schema_definition_comparison_instruction(self, prompt: str):
        """Prompt instructs comparing elements against schema definition."""
        assert "schema definition" in prompt.lower()

    def test_severity_criteria_for_partial(self, prompt: str):
        """Prompt includes severity criteria for partial elements."""
        assert "high" in prompt
        assert "medium" in prompt
        assert "low" in prompt

    def test_actionable_description_instruction(self, prompt: str):
        """Prompt requires descriptions to state what additional content is expected."""
        assert "additional content" in prompt.lower()


class TestCompletenessEvaluationV1OutputSchema:
    """Tests that the prompt instructs structured JSON output (Req 10.8)."""

    @pytest.fixture
    def prompt(self) -> str:
        return completeness_evaluation_v1.build(
            elements_json="[]",
            schema_json="[]",
        )

    def test_json_output_instruction(self, prompt: str):
        """Prompt instructs the LLM to return JSON."""
        assert "JSON" in prompt

    def test_respond_only_json(self, prompt: str):
        """Prompt tells LLM to respond only with JSON — no extra text."""
        assert "Respond ONLY with the JSON object" in prompt

    def test_output_schema_includes_assessments(self, prompt: str):
        """Output schema specifies the assessments array."""
        assert '"assessments"' in prompt

    def test_output_schema_includes_classification(self, prompt: str):
        """Output schema specifies the classification field."""
        assert '"classification"' in prompt

    def test_output_schema_includes_expected_element_name(self, prompt: str):
        """Output schema specifies the expected_element_name field."""
        assert '"expected_element_name"' in prompt

    def test_output_schema_includes_description(self, prompt: str):
        """Output schema specifies the description field."""
        assert '"description"' in prompt

    def test_output_schema_includes_severity(self, prompt: str):
        """Output schema specifies the severity field."""
        assert '"severity"' in prompt


class TestCompletenessEvaluationV1DataMinimization:
    """Tests that the prompt excludes user metadata (Req 9.2, 10.7)."""

    @pytest.fixture
    def prompt(self) -> str:
        return completeness_evaluation_v1.build(
            elements_json='[{"id": "elem-001", "content": "System purpose"}]',
            schema_json='[{"name": "propósito", "description": "Document purpose"}]',
        )

    def test_no_user_id_slot(self, prompt: str):
        """Prompt must not contain user_id placeholder or slot."""
        assert "user_id" not in prompt

    def test_no_session_id_slot(self, prompt: str):
        """Prompt must not contain session_id placeholder or slot."""
        assert "session_id" not in prompt

    def test_no_account_reference(self, prompt: str):
        """Prompt must not reference user account information as input data."""
        assert "account_id" not in prompt
        assert "user_account" not in prompt
        assert "account_name" not in prompt

    def test_no_usage_history(self, prompt: str):
        """Prompt must not contain usage history references."""
        assert "usage_history" not in prompt

    def test_no_session_history(self, prompt: str):
        """Prompt must not contain session history references."""
        assert "session_history" not in prompt

    def test_no_document_id_in_prompt(self, prompt: str):
        """Prompt must not include document_id — that's runtime metadata (Req 9.2)."""
        assert "document_id" not in prompt


class TestCompletenessEvaluationV1Build:
    """Tests for the build() function behavior."""

    def test_build_returns_string(self):
        result = completeness_evaluation_v1.build("[]", "[]")
        assert isinstance(result, str)

    def test_build_with_empty_inputs(self):
        """Build handles empty JSON arrays without error."""
        result = completeness_evaluation_v1.build("[]", "[]")
        assert isinstance(result, str)
        assert "partial" in result.lower()

    def test_build_preserves_elements_content(self):
        """Build includes the full elements JSON in the prompt."""
        elements = '[{"id": "elem-001", "content": "Detailed system purpose"}]'
        result = completeness_evaluation_v1.build(elements, "[]")
        assert elements in result

    def test_build_preserves_schema_content(self):
        """Build includes the full schema JSON in the prompt."""
        schema = '[{"name": "propósito", "description": "Document purpose and goal"}]'
        result = completeness_evaluation_v1.build("[]", schema)
        assert schema in result
