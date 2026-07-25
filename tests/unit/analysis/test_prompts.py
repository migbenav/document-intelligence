"""Unit tests for prompt templates (type inference and extraction).

Verifies:
- Prompt includes only document text (no user metadata or session info)
- Version identifier is accessible
- All valid types are mentioned in prompt instructions
- Extraction prompt includes taxonomy and relationship vocabulary
- Extraction prompt requires verbatim evidence per element

Requirements validated: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 5.1, 6.1, 10.1
"""

import pytest

from app.analysis.prompts import extraction_v1, type_inference_v1


class TestTypeInferenceV1Version:
    """Tests for the VERSION constant (Req 2.2)."""

    def test_version_constant_exists(self):
        assert hasattr(type_inference_v1, "VERSION")

    def test_version_is_string(self):
        assert isinstance(type_inference_v1.VERSION, str)

    def test_version_value(self):
        assert type_inference_v1.VERSION == "type-inference-v1"


class TestTypeInferenceV1Build:
    """Tests for the build() function (Req 2.1, 2.4, 3.1)."""

    @pytest.fixture
    def sample_ir_text(self) -> str:
        return (
            "# Product Requirements Document\n\n"
            "## Purpose\n"
            "This document defines the requirements for the new user authentication system.\n\n"
            "## User Stories\n"
            "As a user, I want to log in with my email and password.\n"
        )

    def test_build_returns_string(self, sample_ir_text: str):
        result = type_inference_v1.build(sample_ir_text)
        assert isinstance(result, str)

    def test_prompt_includes_document_text(self, sample_ir_text: str):
        result = type_inference_v1.build(sample_ir_text)
        assert sample_ir_text in result

    def test_all_valid_types_mentioned_in_prompt(self, sample_ir_text: str):
        """All four valid document types must be mentioned in the prompt (Req 3.1)."""
        result = type_inference_v1.build(sample_ir_text)
        assert "prd" in result
        assert "technical_spec" in result
        assert "policy_process" in result
        assert "generic" in result

    def test_prompt_requests_json_output(self, sample_ir_text: str):
        """Prompt instructs the LLM to return JSON with the expected keys."""
        result = type_inference_v1.build(sample_ir_text)
        assert "document_type" in result
        assert "justification" in result
        assert "JSON" in result

    def test_prompt_excludes_user_metadata(self, sample_ir_text: str):
        """Prompt must not include user metadata or session info (Req 2.4)."""
        result = type_inference_v1.build(sample_ir_text)
        # The prompt should not contain placeholders or references to user metadata
        assert "user_id" not in result
        assert "session_id" not in result
        assert "account" not in result.lower() or "account" in sample_ir_text.lower()
        assert "email" not in result.lower() or "email" in sample_ir_text.lower()

    def test_prompt_contains_only_document_text_and_instructions(self, sample_ir_text: str):
        """The prompt should consist of system instructions and the document text only (Req 2.4)."""
        result = type_inference_v1.build(sample_ir_text)
        # After removing the document text, no user/session metadata should remain
        without_sample = result.replace(sample_ir_text, "")
        # Should not contain any metadata-like patterns
        assert "user_name" not in without_sample
        assert "session_history" not in without_sample
        assert "usage_history" not in without_sample

    def test_empty_ir_text(self):
        """Build handles empty text without error."""
        result = type_inference_v1.build("")
        assert isinstance(result, str)
        # Valid types should still be mentioned
        assert "prd" in result
        assert "generic" in result

    def test_long_ir_text_preserved(self):
        """Build preserves the full text passed to it (caller responsible for truncation)."""
        long_text = "x" * 5000
        result = type_inference_v1.build(long_text)
        assert long_text in result


class TestTypeInferenceV1ValidTypes:
    """Tests that the module exposes valid type information."""

    def test_valid_types_tuple_exists(self):
        assert hasattr(type_inference_v1, "_VALID_TYPES")

    def test_valid_types_contains_all_four(self):
        assert "prd" in type_inference_v1._VALID_TYPES
        assert "technical_spec" in type_inference_v1._VALID_TYPES
        assert "policy_process" in type_inference_v1._VALID_TYPES
        assert "generic" in type_inference_v1._VALID_TYPES

    def test_valid_types_count(self):
        assert len(type_inference_v1._VALID_TYPES) == 4


# =============================================================================
# Extraction Prompt Template Tests (extraction_v1)
# =============================================================================


class TestExtractionV1Version:
    """Tests for the VERSION constant (Req 2.2)."""

    def test_version_constant_exists(self):
        assert hasattr(extraction_v1, "VERSION")

    def test_version_is_string(self):
        assert isinstance(extraction_v1.VERSION, str)

    def test_version_value(self):
        assert extraction_v1.VERSION == "extraction-v1"


class TestExtractionV1Taxonomy:
    """Tests that the extraction prompt includes the fixed taxonomy (Req 2.3)."""

    @pytest.fixture
    def prompt(self) -> str:
        return extraction_v1.build(
            ir_text="Sample document text.",
            document_type="prd",
            structural_contexts=[],
        )

    def test_taxonomy_proposito(self, prompt: str):
        assert "proposito" in prompt

    def test_taxonomy_concepto(self, prompt: str):
        assert "concepto" in prompt

    def test_taxonomy_actor(self, prompt: str):
        assert "actor" in prompt

    def test_taxonomy_regla(self, prompt: str):
        assert "regla" in prompt

    def test_taxonomy_proceso(self, prompt: str):
        assert "proceso" in prompt

    def test_taxonomy_restriccion(self, prompt: str):
        assert "restriccion" in prompt

    def test_all_taxonomy_types_in_module(self):
        """The module exposes the full taxonomy tuple."""
        assert extraction_v1._TAXONOMY == (
            "proposito",
            "concepto",
            "actor",
            "regla",
            "proceso",
            "restriccion",
        )


class TestExtractionV1RelationshipVocabulary:
    """Tests that the extraction prompt includes the relationship vocabulary (Req 2.3)."""

    @pytest.fixture
    def prompt(self) -> str:
        return extraction_v1.build(
            ir_text="Sample document text.",
            document_type="technical_spec",
            structural_contexts=[],
        )

    def test_relationship_constrains(self, prompt: str):
        assert "constrains" in prompt

    def test_relationship_participates_in(self, prompt: str):
        assert "participates_in" in prompt

    def test_relationship_depends_on(self, prompt: str):
        assert "depends_on" in prompt

    def test_relationship_contradicts(self, prompt: str):
        assert "contradicts" in prompt

    def test_all_relationship_types_in_module(self):
        """The module exposes the full relationship vocabulary tuple."""
        assert extraction_v1._RELATIONSHIP_VOCABULARY == (
            "constrains",
            "participates_in",
            "depends_on",
            "contradicts",
        )


class TestExtractionV1EvidenceInstruction:
    """Tests that the extraction prompt requires verbatim evidence (Req 2.5)."""

    @pytest.fixture
    def prompt(self) -> str:
        return extraction_v1.build(
            ir_text="The system shall process documents.",
            document_type="generic",
            structural_contexts=[],
        )

    def test_evidence_keyword_present(self, prompt: str):
        """Prompt must instruct the LLM to include evidence."""
        assert "evidence" in prompt.lower()

    def test_verbatim_instruction_present(self, prompt: str):
        """Prompt must instruct verbatim/exact text copying."""
        assert "verbatim" in prompt.lower()

    def test_source_ref_evidence_in_schema(self, prompt: str):
        """The output schema includes the evidence field in source_ref."""
        assert "source_ref" in prompt
        assert '"evidence"' in prompt


class TestExtractionV1DataMinimization:
    """Tests that the prompt excludes user metadata (Req 2.4)."""

    @pytest.fixture
    def prompt(self) -> str:
        return extraction_v1.build(
            ir_text="Document about authentication flows.",
            document_type="prd",
            structural_contexts=[{"chunk_id": "chunk-001", "section": "# Auth"}],
        )

    def test_no_user_id_slot(self, prompt: str):
        """Prompt must not contain user_id placeholder or slot."""
        assert "user_id" not in prompt

    def test_no_session_id_slot(self, prompt: str):
        """Prompt must not contain session_id placeholder or slot."""
        assert "session_id" not in prompt

    def test_no_account_reference(self, prompt: str):
        """Prompt must not reference user account information as input data."""
        # Only check the instructions portion, not the document text
        instructions_part = prompt.split("--- DOCUMENT TEXT ---")[0]
        # The word "account" may appear in instructions telling the LLM what NOT to include.
        # We check for actual account data placeholders or slots that would be filled.
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
        """Prompt must not include document_id — that's runtime metadata (Req 2.4)."""
        assert "document_id" not in prompt


class TestExtractionV1Build:
    """Tests for the build() function behavior (Req 2.1, 5.1, 10.1)."""

    def test_build_returns_string(self):
        result = extraction_v1.build("text", "prd", [])
        assert isinstance(result, str)

    def test_build_includes_ir_text(self):
        ir_text = "This is the full document IR content for analysis."
        result = extraction_v1.build(ir_text, "generic", [])
        assert ir_text in result

    def test_build_includes_document_type(self):
        result = extraction_v1.build("text", "technical_spec", [])
        assert "technical_spec" in result

    def test_build_includes_structural_context(self):
        contexts = [
            {"chunk_id": "chunk-001", "section": "# Introduction", "page": 1},
            {"chunk_id": "chunk-002", "section": "# Requirements", "page": 2},
        ]
        result = extraction_v1.build("text", "prd", contexts)
        assert "chunk-001" in result
        assert "Introduction" in result
        assert "chunk-002" in result
        assert "Requirements" in result

    def test_build_empty_structural_contexts(self):
        """Build handles empty structural contexts gracefully."""
        result = extraction_v1.build("text", "prd", [])
        assert "No structural context available" in result

    def test_build_empty_ir_text(self):
        """Build handles empty text without error."""
        result = extraction_v1.build("", "generic", [])
        assert isinstance(result, str)
        # Taxonomy should still be present in instructions
        assert "proposito" in result

    def test_prompt_requests_json_output(self):
        """Prompt instructs the LLM to return JSON (Req 10.1)."""
        result = extraction_v1.build("text", "prd", [])
        assert "JSON" in result

    def test_prompt_specifies_schema_constraints(self):
        """Prompt includes schema structure to constrain output (Req 10.1)."""
        result = extraction_v1.build("text", "prd", [])
        # The schema section should show the expected JSON structure
        assert '"id"' in result
        assert '"type"' in result
        assert '"name"' in result
        assert '"content"' in result
        assert '"source_ref"' in result
        assert '"relations"' in result

    def test_prompt_instructs_only_json_response(self):
        """Prompt tells LLM to respond only with JSON — no extra text (Req 10.1)."""
        result = extraction_v1.build("text", "prd", [])
        assert "Respond ONLY with the JSON object" in result

    def test_document_type_prd_context(self):
        """Document type 'prd' is reflected in extraction priorities."""
        result = extraction_v1.build("text", "prd", [])
        assert "prd" in result

    def test_document_type_generic_context(self):
        """Document type 'generic' is reflected in extraction priorities."""
        result = extraction_v1.build("text", "generic", [])
        assert "generic" in result
