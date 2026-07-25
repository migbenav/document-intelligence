"""Unit tests for quality analysis prompt templates.

Verifies:
- Version identifier is accessible
- Ambiguity detection prompt mentions all four ambiguity categories
- Interpretation requirement (at least 2 plausible interpretations) is present
- Actionability instruction is present (concrete actions, not problem restatements)
- Maximum 300 character description constraint is mentioned
- All four suggestion categories are listed
- No user metadata or session info included
- Source_ref requirement is present

Requirements validated: 2.1, 2.2, 2.3, 4.1, 4.2, 4.3, 9.2, 10.1, 10.7, 10.8
"""

import pytest

from app.analysis.prompts import ambiguity_detection_v1, suggestion_generation_v1


# =============================================================================
# Suggestion Generation Prompt Template Tests (suggestion_generation_v1)
# =============================================================================


class TestSuggestionGenerationV1Version:
    """Tests for the VERSION constant (Req 10.8)."""

    def test_version_constant_exists(self):
        assert hasattr(suggestion_generation_v1, "VERSION")

    def test_version_is_string(self):
        assert isinstance(suggestion_generation_v1.VERSION, str)

    def test_version_value(self):
        assert suggestion_generation_v1.VERSION == "suggestion-v1"


class TestSuggestionGenerationV1Actionability:
    """Tests that the prompt enforces actionable suggestions (Req 4.3)."""

    @pytest.fixture
    def prompt(self) -> str:
        return suggestion_generation_v1.build(
            findings_json='[{"id": "inc-001", "type": "contradiction", "severity": "high"}]',
            elements_json='[{"id": "elem-001", "type": "concepto", "name": "Auth"}]',
            ir_text="The system requires user authentication via OAuth2.",
        )

    def test_actionability_instruction_present(self, prompt: str):
        """Prompt must instruct the LLM to generate actionable suggestions."""
        prompt_lower = prompt.lower()
        assert "actionable" in prompt_lower

    def test_concrete_action_instruction(self, prompt: str):
        """Prompt must instruct concrete actions, not problem restatements."""
        prompt_lower = prompt.lower()
        assert "concrete" in prompt_lower

    def test_what_to_do_instruction(self, prompt: str):
        """Prompt emphasizes what to do vs what is wrong."""
        assert "WHAT TO DO" in prompt or "what to do" in prompt.lower()

    def test_not_restatement_instruction(self, prompt: str):
        """Prompt explicitly tells LLM not to restate problems."""
        prompt_lower = prompt.lower()
        assert "restatement" in prompt_lower or "not what is wrong" in prompt_lower


class TestSuggestionGenerationV1MaxLength:
    """Tests that the prompt enforces max 300 character descriptions (Req 4.2)."""

    @pytest.fixture
    def prompt(self) -> str:
        return suggestion_generation_v1.build(
            findings_json="[]",
            elements_json="[]",
            ir_text="Sample document text.",
        )

    def test_max_300_chars_mentioned(self, prompt: str):
        """Prompt must mention the 300 character limit for descriptions."""
        assert "300" in prompt

    def test_max_characters_constraint(self, prompt: str):
        """Prompt references character limit in context of descriptions."""
        assert "300 character" in prompt.lower() or "max 300" in prompt.lower()


class TestSuggestionGenerationV1Categories:
    """Tests that all four suggestion categories are listed (Req 4.2)."""

    @pytest.fixture
    def prompt(self) -> str:
        return suggestion_generation_v1.build(
            findings_json="[]",
            elements_json="[]",
            ir_text="Document about system design.",
        )

    def test_category_structure(self, prompt: str):
        assert "structure" in prompt

    def test_category_clarity(self, prompt: str):
        assert "clarity" in prompt

    def test_category_completeness(self, prompt: str):
        assert "completeness" in prompt

    def test_category_consistency(self, prompt: str):
        assert "consistency" in prompt

    def test_categories_tuple_exposed(self):
        """Module exposes the valid categories."""
        assert suggestion_generation_v1._CATEGORIES == (
            "structure",
            "clarity",
            "completeness",
            "consistency",
        )


class TestSuggestionGenerationV1SourceRef:
    """Tests that the prompt requires source_refs (Req 7.6)."""

    @pytest.fixture
    def prompt(self) -> str:
        return suggestion_generation_v1.build(
            findings_json="[]",
            elements_json="[]",
            ir_text="Sample text.",
        )

    def test_source_ref_requirement(self, prompt: str):
        """Prompt must require at least one source_ref per suggestion."""
        assert "source_ref" in prompt.lower() or "source_refs" in prompt.lower()

    def test_at_least_one_source_ref(self, prompt: str):
        """Prompt must state at least one source_ref is required."""
        prompt_lower = prompt.lower()
        assert "at least one source_ref" in prompt_lower or (
            "at least one" in prompt_lower and "source_ref" in prompt_lower
        )


class TestSuggestionGenerationV1DataMinimization:
    """Tests that the prompt excludes user metadata (Req 9.2, 10.7)."""

    @pytest.fixture
    def prompt(self) -> str:
        return suggestion_generation_v1.build(
            findings_json='[{"id": "inc-001"}]',
            elements_json='[{"id": "elem-001", "name": "Test"}]',
            ir_text="The system shall process requests efficiently.",
        )

    def test_no_user_id_slot(self, prompt: str):
        """Prompt must not contain user_id placeholder or slot."""
        assert "user_id" not in prompt

    def test_no_session_id_slot(self, prompt: str):
        """Prompt must not contain session_id placeholder or slot."""
        assert "session_id" not in prompt

    def test_no_account_metadata(self, prompt: str):
        """Prompt must not reference account information."""
        instructions_part = prompt.split("--- QUALITY FINDINGS ---")[0]
        assert "account_id" not in instructions_part
        assert "user_account" not in instructions_part

    def test_no_usage_history(self, prompt: str):
        """Prompt must not contain usage history references."""
        assert "usage_history" not in prompt

    def test_no_session_history(self, prompt: str):
        """Prompt must not contain session history references."""
        assert "session_history" not in prompt

    def test_no_document_id_in_instructions(self, prompt: str):
        """Prompt instructions must not include document_id (runtime metadata)."""
        instructions_part = prompt.split("--- QUALITY FINDINGS ---")[0]
        assert "document_id" not in instructions_part


class TestSuggestionGenerationV1Build:
    """Tests for the build() function behavior (Req 10.1)."""

    def test_build_returns_string(self):
        result = suggestion_generation_v1.build("[]", "[]", "text")
        assert isinstance(result, str)

    def test_build_includes_findings(self):
        findings = '[{"id": "inc-001", "type": "contradiction"}]'
        result = suggestion_generation_v1.build(findings, "[]", "text")
        assert findings in result

    def test_build_includes_elements(self):
        elements = '[{"id": "elem-001", "type": "concepto", "name": "API Gateway"}]'
        result = suggestion_generation_v1.build("[]", elements, "text")
        assert elements in result

    def test_build_includes_ir_text(self):
        ir_text = "The authentication system handles user login and session management."
        result = suggestion_generation_v1.build("[]", "[]", ir_text)
        assert ir_text in result

    def test_build_empty_inputs(self):
        """Build handles empty inputs without error."""
        result = suggestion_generation_v1.build("", "", "")
        assert isinstance(result, str)
        # Categories should still be present in instructions
        assert "structure" in result
        assert "clarity" in result

    def test_prompt_requests_json_output(self):
        """Prompt instructs the LLM to return JSON (Req 10.1)."""
        result = suggestion_generation_v1.build("[]", "[]", "text")
        assert "JSON" in result

    def test_prompt_specifies_json_schema(self):
        """Prompt includes the expected JSON output schema."""
        result = suggestion_generation_v1.build("[]", "[]", "text")
        assert '"suggestions"' in result
        assert '"id"' in result
        assert '"description"' in result
        assert '"category"' in result
        assert '"priority"' in result
        assert '"source_refs"' in result

    def test_prompt_instructs_only_json_response(self):
        """Prompt tells LLM to respond only with JSON — no extra text."""
        result = suggestion_generation_v1.build("[]", "[]", "text")
        assert "Respond ONLY with the JSON object" in result

    def test_priority_levels_mentioned(self):
        """Prompt mentions all three priority levels."""
        result = suggestion_generation_v1.build("[]", "[]", "text")
        # Priority levels in context of mapping
        assert "high" in result
        assert "medium" in result
        assert "low" in result

    def test_max_20_suggestions_mentioned(self):
        """Prompt mentions the maximum of 20 suggestions constraint."""
        result = suggestion_generation_v1.build("[]", "[]", "text")
        assert "20" in result


# =============================================================================
# Contradiction Detection Prompt Template Tests (contradiction_detection_v1)
# =============================================================================

from app.analysis.prompts import contradiction_detection_v1


class TestContradictionDetectionV1Version:
    """Tests for the VERSION constant (Req 10.8)."""

    def test_version_constant_exists(self):
        assert hasattr(contradiction_detection_v1, "VERSION")

    def test_version_is_string(self):
        assert isinstance(contradiction_detection_v1.VERSION, str)

    def test_version_value(self):
        assert contradiction_detection_v1.VERSION == "contradiction-v1"


class TestContradictionDetectionV1SeverityCriteria:
    """Tests that the prompt includes severity criteria (Req 1.2)."""

    @pytest.fixture
    def prompt(self) -> str:
        return contradiction_detection_v1.build(
            elements_json='[{"id": "elem-001", "type": "regla", "name": "Rule A"}]',
            relationships_json="[]",
            ir_text="Sample document text.",
        )

    def test_severity_high_definition(self, prompt: str):
        """Prompt must define high severity as mutually exclusive facts."""
        assert "high" in prompt
        assert "mutually exclusive" in prompt.lower()

    def test_severity_medium_definition(self, prompt: str):
        """Prompt must define medium severity as incompatible intent."""
        assert "medium" in prompt
        assert "incompatible intent" in prompt.lower()

    def test_severity_low_definition(self, prompt: str):
        """Prompt must define low severity as minor wording tensions."""
        assert "low" in prompt
        assert "wording tensions" in prompt.lower()

    def test_all_severity_levels_present(self, prompt: str):
        """All three severity levels must be defined in the prompt."""
        assert "high" in prompt
        assert "medium" in prompt
        assert "low" in prompt


class TestContradictionDetectionV1DataMinimization:
    """Tests that the prompt excludes user metadata (Req 9.2, 10.7)."""

    @pytest.fixture
    def prompt(self) -> str:
        return contradiction_detection_v1.build(
            elements_json='[{"id": "elem-001", "type": "concepto", "name": "Auth"}]',
            relationships_json='[{"source_id": "elem-001", "target_id": "elem-002", "type": "contradicts"}]',
            ir_text="The system requires user authentication via OAuth2.",
        )

    def test_no_user_id_slot(self, prompt: str):
        """Prompt must not contain user_id placeholder or slot."""
        assert "user_id" not in prompt

    def test_no_session_id_slot(self, prompt: str):
        """Prompt must not contain session_id placeholder or slot."""
        assert "session_id" not in prompt

    def test_no_account_id_slot(self, prompt: str):
        """Prompt must not contain account_id placeholder or slot."""
        assert "account_id" not in prompt

    def test_no_user_account_slot(self, prompt: str):
        """Prompt must not contain user_account reference."""
        assert "user_account" not in prompt

    def test_no_usage_history(self, prompt: str):
        """Prompt must not contain usage history references."""
        assert "usage_history" not in prompt

    def test_no_session_history(self, prompt: str):
        """Prompt must not contain session history references."""
        assert "session_history" not in prompt

    def test_no_document_id_in_instructions(self, prompt: str):
        """Prompt instructions must not include document_id — that's runtime metadata."""
        instructions_part = prompt.split("--- KNOWLEDGE MODEL ELEMENTS ---")[0]
        assert "document_id" not in instructions_part


class TestContradictionDetectionV1OutputSchema:
    """Tests that the prompt includes output schema instructions (Req 10.1, 10.2)."""

    @pytest.fixture
    def prompt(self) -> str:
        return contradiction_detection_v1.build(
            elements_json='[{"id": "elem-001"}]',
            relationships_json="[]",
            ir_text="Document text here.",
        )

    def test_json_output_instructed(self, prompt: str):
        """Prompt must instruct the LLM to return JSON."""
        assert "JSON" in prompt

    def test_schema_includes_type_field(self, prompt: str):
        """Output schema must specify the type field."""
        assert '"type"' in prompt

    def test_schema_specifies_contradiction_type(self, prompt: str):
        """Output schema must specify type as contradiction."""
        assert '"contradiction"' in prompt

    def test_schema_includes_description_field(self, prompt: str):
        """Output schema must include description field."""
        assert '"description"' in prompt

    def test_schema_includes_severity_field(self, prompt: str):
        """Output schema must include severity field."""
        assert '"severity"' in prompt

    def test_schema_includes_affected_element_ids(self, prompt: str):
        """Output schema must include affected_element_ids field."""
        assert '"affected_element_ids"' in prompt

    def test_schema_includes_source_refs(self, prompt: str):
        """Output schema must include source_refs field."""
        assert '"source_refs"' in prompt

    def test_schema_includes_evidence_field(self, prompt: str):
        """Output schema must include evidence field in source_refs."""
        assert '"evidence"' in prompt

    def test_schema_includes_chunk_id(self, prompt: str):
        """Output schema must include chunk_id in source_refs."""
        assert '"chunk_id"' in prompt

    def test_only_json_response_instruction(self, prompt: str):
        """Prompt must instruct LLM to respond only with JSON."""
        assert "Respond ONLY with the JSON object" in prompt


class TestContradictionDetectionV1Build:
    """Tests for the build() function behavior (Req 1.1, 1.4)."""

    def test_build_returns_string(self):
        result = contradiction_detection_v1.build("[]", "[]", "text")
        assert isinstance(result, str)

    def test_build_includes_elements_json(self):
        elements = '[{"id": "elem-001", "type": "regla", "name": "Performance"}]'
        result = contradiction_detection_v1.build(elements, "[]", "text")
        assert elements in result

    def test_build_includes_relationships_json(self):
        rels = '[{"source_id": "elem-001", "target_id": "elem-002", "type": "contradicts"}]'
        result = contradiction_detection_v1.build("[]", rels, "text")
        assert rels in result

    def test_build_includes_ir_text(self):
        ir_text = "The maximum response time is 200ms for all endpoints."
        result = contradiction_detection_v1.build("[]", "[]", ir_text)
        assert ir_text in result

    def test_build_empty_inputs(self):
        """Build handles empty inputs without error."""
        result = contradiction_detection_v1.build("", "", "")
        assert isinstance(result, str)
        # Severity criteria should still be present
        assert "high" in result
        assert "medium" in result
        assert "low" in result

    def test_build_has_findings_wrapper(self):
        """Output schema wraps findings in a 'findings' array."""
        result = contradiction_detection_v1.build("[]", "[]", "text")
        assert '"findings"' in result

    def test_minimum_two_source_refs_instructed(self):
        """Prompt instructs that each contradiction needs at least 2 source_refs."""
        result = contradiction_detection_v1.build("[]", "[]", "text")
        assert "at least 2 source_refs" in result

    def test_minimum_two_affected_elements_instructed(self):
        """Prompt instructs that each contradiction needs at least 2 affected_element_ids."""
        result = contradiction_detection_v1.build("[]", "[]", "text")
        assert "at least 2 affected_element_ids" in result


# =============================================================================
# Ambiguity Detection Prompt Template Tests (ambiguity_detection_v1)
# =============================================================================


class TestAmbiguityDetectionV1Version:
    """Tests for the VERSION constant (Req 10.8)."""

    def test_version_constant_exists(self):
        assert hasattr(ambiguity_detection_v1, "VERSION")

    def test_version_is_string(self):
        assert isinstance(ambiguity_detection_v1.VERSION, str)

    def test_version_value(self):
        assert ambiguity_detection_v1.VERSION == "ambiguity-v1"


class TestAmbiguityDetectionV1AmbiguityCategories:
    """Tests that the prompt mentions all four ambiguity categories (Req 2.3)."""

    @pytest.fixture
    def prompt(self) -> str:
        return ambiguity_detection_v1.build(
            elements_json='[{"id": "elem-001", "type": "concepto", "name": "System"}]',
            ir_text="The system shall handle requests quickly.",
        )

    def test_undefined_terms_category(self, prompt: str):
        """Prompt must instruct detection of undefined terms."""
        assert "undefined" in prompt.lower()
        assert "term" in prompt.lower()

    def test_vague_quantifiers_category(self, prompt: str):
        """Prompt must instruct detection of vague quantifiers."""
        assert "vague" in prompt.lower()
        assert "quantifier" in prompt.lower()

    def test_unclear_pronoun_antecedents_category(self, prompt: str):
        """Prompt must instruct detection of unclear pronoun antecedents."""
        assert "pronoun" in prompt.lower()
        assert "antecedent" in prompt.lower()

    def test_unspecified_conditions_category(self, prompt: str):
        """Prompt must instruct detection of unspecified conditions."""
        assert "unspecified" in prompt.lower()
        assert "condition" in prompt.lower()

    def test_all_four_categories_in_schema(self, prompt: str):
        """Output schema must reference all four category values."""
        assert "undefined_term" in prompt
        assert "vague_quantifier" in prompt
        assert "unclear_pronoun_antecedent" in prompt
        assert "unspecified_condition" in prompt


class TestAmbiguityDetectionV1InterpretationRequirement:
    """Tests that the prompt requires at least 2 interpretations per finding (Req 2.2)."""

    @pytest.fixture
    def prompt(self) -> str:
        return ambiguity_detection_v1.build(
            elements_json='[]',
            ir_text="Sample text for analysis.",
        )

    def test_interpretation_requirement_present(self, prompt: str):
        """Prompt must explicitly require multiple interpretations."""
        assert "2" in prompt
        assert "interpretation" in prompt.lower()

    def test_plausible_interpretations_language(self, prompt: str):
        """Prompt should use 'plausible interpretations' language."""
        assert "plausible interpretation" in prompt.lower()

    def test_at_least_two_interpretations_instruction(self, prompt: str):
        """Prompt must require at least 2 interpretations for every finding."""
        assert "at least 2" in prompt


class TestAmbiguityDetectionV1SeverityCriteria:
    """Tests that the prompt includes severity criteria (Req 2.2)."""

    @pytest.fixture
    def prompt(self) -> str:
        return ambiguity_detection_v1.build(
            elements_json='[]',
            ir_text="Sample text.",
        )

    def test_high_severity_defined(self, prompt: str):
        """High severity criteria should reference blocking comprehension."""
        assert "high" in prompt.lower()
        assert "block" in prompt.lower()
        assert "comprehension" in prompt.lower()

    def test_medium_severity_defined(self, prompt: str):
        """Medium severity criteria should reference creating uncertainty."""
        assert "medium" in prompt.lower()
        assert "uncertainty" in prompt.lower()

    def test_low_severity_defined(self, prompt: str):
        """Low severity criteria should reference stylistic imprecision."""
        assert "low" in prompt.lower()
        assert "stylistic" in prompt.lower()


class TestAmbiguityDetectionV1DataMinimization:
    """Tests that the prompt excludes user metadata (Req 9.2, 10.7)."""

    @pytest.fixture
    def prompt(self) -> str:
        return ambiguity_detection_v1.build(
            elements_json='[{"id": "elem-001", "type": "regla", "name": "Rule"}]',
            ir_text="Document content about authentication.",
        )

    def test_no_user_id_slot(self, prompt: str):
        """Prompt must not contain user_id placeholder or slot."""
        assert "user_id" not in prompt

    def test_no_session_id_slot(self, prompt: str):
        """Prompt must not contain session_id placeholder or slot."""
        assert "session_id" not in prompt

    def test_no_account_metadata(self, prompt: str):
        """Prompt must not reference account information as input data."""
        instructions_part = prompt.split("--- DOCUMENT TEXT ---")[0]
        assert "account_id" not in instructions_part
        assert "user_account" not in instructions_part
        assert "account_name" not in instructions_part

    def test_no_usage_history(self, prompt: str):
        """Prompt must not contain usage history references."""
        assert "usage_history" not in prompt

    def test_no_session_history(self, prompt: str):
        """Prompt must not contain session history references."""
        assert "session_history" not in prompt

    def test_no_document_id_in_prompt(self, prompt: str):
        """Prompt must not include document_id — that's runtime metadata."""
        assert "document_id" not in prompt


class TestAmbiguityDetectionV1Build:
    """Tests for the build() function behavior (Req 2.1, 10.1)."""

    def test_build_returns_string(self):
        result = ambiguity_detection_v1.build("[]", "text")
        assert isinstance(result, str)

    def test_build_includes_elements_json(self):
        elements = '[{"id": "elem-001", "type": "concepto", "name": "API Gateway"}]'
        result = ambiguity_detection_v1.build(elements, "text")
        assert elements in result

    def test_build_includes_ir_text(self):
        ir_text = "The system shall process all incoming requests in a timely manner."
        result = ambiguity_detection_v1.build("[]", ir_text)
        assert ir_text in result

    def test_build_empty_elements(self):
        """Build handles empty elements JSON without error."""
        result = ambiguity_detection_v1.build("[]", "Some document text.")
        assert isinstance(result, str)
        assert "ambiguity" in result.lower()

    def test_build_empty_ir_text(self):
        """Build handles empty IR text without error."""
        result = ambiguity_detection_v1.build("[]", "")
        assert isinstance(result, str)

    def test_prompt_requests_json_output(self):
        """Prompt instructs the LLM to return JSON (Req 10.1)."""
        result = ambiguity_detection_v1.build("[]", "text")
        assert "JSON" in result

    def test_prompt_specifies_output_schema(self):
        """Prompt includes output schema structure (Req 10.1)."""
        result = ambiguity_detection_v1.build("[]", "text")
        assert '"ambiguities"' in result
        assert '"id"' in result
        assert '"category"' in result
        assert '"description"' in result
        assert '"severity"' in result
        assert '"source_ref"' in result

    def test_prompt_instructs_only_json_response(self):
        """Prompt tells LLM to respond only with JSON (Req 10.1)."""
        result = ambiguity_detection_v1.build("[]", "text")
        assert "Respond ONLY with the JSON object" in result

    def test_evidence_requirement_present(self):
        """Prompt requires verbatim evidence in source_ref."""
        result = ambiguity_detection_v1.build("[]", "text")
        assert "evidence" in result.lower()
        assert "verbatim" in result.lower()

    def test_max_description_length_mentioned(self):
        """Prompt specifies max 500 character description length."""
        result = ambiguity_detection_v1.build("[]", "text")
        assert "500" in result


class TestAmbiguityDetectionV1CategoriesTuple:
    """Tests that the module exposes category information."""

    def test_categories_tuple_exists(self):
        assert hasattr(ambiguity_detection_v1, "_AMBIGUITY_CATEGORIES")

    def test_categories_contains_all_four(self):
        assert "undefined_term" in ambiguity_detection_v1._AMBIGUITY_CATEGORIES
        assert "vague_quantifier" in ambiguity_detection_v1._AMBIGUITY_CATEGORIES
        assert "unclear_pronoun_antecedent" in ambiguity_detection_v1._AMBIGUITY_CATEGORIES
        assert "unspecified_condition" in ambiguity_detection_v1._AMBIGUITY_CATEGORIES

    def test_categories_count(self):
        assert len(ambiguity_detection_v1._AMBIGUITY_CATEGORIES) == 4
