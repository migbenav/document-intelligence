"""Unit tests for Build Index v2 — functional comprehension.

Tests cover:
- Prompt includes classification and functional instructions
- IndexResult with functional_group and original_headings parses correctly
- document_purpose field is present in result
- Role values include new vocabulary (enables, restricts, controls, delegates)

Requirements: Req 1 (criteria 1-8)
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.analysis.llm_client import LLMResponse
from app.analysis.on_demand.analyzer_response import AnalyzerResponse
from app.analysis.on_demand.index_analyzer import IndexAnalyzer
from app.analysis.on_demand.models import IndexResult, StructureNode
from app.analysis.on_demand.prompts.build_index_v2 import (
    PROMPT_TEMPLATE,
    PROMPT_VERSION,
    get_purpose_hint,
)
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    IntermediateRepresentation,
)

pytestmark = pytest.mark.asyncio


# --- Helpers ---


def _make_ir() -> IntermediateRepresentation:
    """Build a minimal IR for testing."""
    return IntermediateRepresentation(
        document_id="doc-v2-001",
        metadata=DocumentMetadata(
            original_filename="reglamento.pdf",
            format=DocumentFormat.PDF,
            size_bytes=4096,
            language=DetectedLanguage.SPANISH,
            upload_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ),
        chunks=[
            ContentChunkModel(
                chunk_id="c1",
                text="Este reglamento establece las normas de convivencia.",
                structural_context={"section": "Introducción"},
                order=0,
            ),
            ContentChunkModel(
                chunk_id="c2",
                text="Los residentes podrán usar las áreas comunes según horario.",
                structural_context={"section": "Uso de áreas comunes"},
                order=1,
            ),
            ContentChunkModel(
                chunk_id="c3",
                text="El administrador controlará el cumplimiento de las normas.",
                structural_context={"section": "Control y fiscalización"},
                order=2,
            ),
        ],
    )


def _valid_v2_response() -> dict:
    """Return a valid IndexResult JSON with v2 fields."""
    return {
        "document_purpose": "Establish coexistence rules for the residential community",
        "tree": [
            {
                "id": "node-1",
                "title": "Purpose and Scope",
                "level": 1,
                "role": "defines",
                "functional_group": "purpose",
                "original_headings": ["Introducción", "Objetivo"],
                "question_answered": "What does this regulation exist to do?",
                "source_ref": {
                    "chunk_ids": ["c1"],
                    "text_excerpt": "Este reglamento establece las normas de convivencia.",
                    "section": "Introducción",
                },
                "children": [],
            },
            {
                "id": "node-2",
                "title": "Usage Permissions",
                "level": 1,
                "role": "enables",
                "functional_group": "execution",
                "original_headings": ["Uso de áreas comunes"],
                "question_answered": "What are residents permitted to do?",
                "source_ref": {
                    "chunk_ids": ["c2"],
                    "text_excerpt": "Los residentes podrán usar las áreas comunes según horario.",
                    "section": "Uso de áreas comunes",
                },
                "children": [],
            },
            {
                "id": "node-3",
                "title": "Oversight and Control",
                "level": 1,
                "role": "controls",
                "functional_group": "control",
                "original_headings": ["Control y fiscalización"],
                "question_answered": "How is compliance monitored?",
                "source_ref": {
                    "chunk_ids": ["c3"],
                    "text_excerpt": "El administrador controlará el cumplimiento de las normas.",
                    "section": "Control y fiscalización",
                },
                "children": [],
            },
        ],
    }


def _make_mock_llm_client(
    response_content: str, model_id: str = "gemini/gemini-2.5-flash"
) -> MagicMock:
    """Create a mock LLMClient that returns the given content."""
    mock_client = MagicMock()
    mock_client.primary_model = "gemini/gemini-2.5-flash"
    mock_client.call = AsyncMock(
        return_value=LLMResponse(content=response_content, model_id=model_id)
    )
    return mock_client


# --- Tests: Prompt includes classification and functional instructions ---


class TestPromptClassificationAndFunctionalInstructions:
    """Verify the prompt includes classification context and functional analysis instructions."""

    async def test_prompt_includes_classification(self):
        """The prompt sent to the LLM includes the document classification."""
        mock_client = _make_mock_llm_client(json.dumps(_valid_v2_response()))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es", classification="normative")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        assert "normative" in prompt

    async def test_prompt_includes_purpose_hint_for_normative(self):
        """Normative classification produces the appropriate purpose hint in prompt."""
        mock_client = _make_mock_llm_client(json.dumps(_valid_v2_response()))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es", classification="normative")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        expected_hint = get_purpose_hint("normative")
        assert expected_hint in prompt

    async def test_prompt_includes_purpose_hint_for_procedure(self):
        """Procedure classification produces the appropriate purpose hint."""
        mock_client = _make_mock_llm_client(json.dumps(_valid_v2_response()))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es", classification="procedure")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        expected_hint = get_purpose_hint("procedure")
        assert expected_hint in prompt

    async def test_prompt_includes_functional_grouping_instructions(self):
        """The prompt contains instructions about functional groupings."""
        mock_client = _make_mock_llm_client(json.dumps(_valid_v2_response()))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es", classification="generic")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        assert "FUNCTIONAL GROUPINGS" in prompt
        assert "Do NOT simply list headings" in prompt

    async def test_prompt_instructs_functional_tree_not_visual(self):
        """The prompt instructs the LLM that the tree represents function, not visual layout."""
        mock_client = _make_mock_llm_client(json.dumps(_valid_v2_response()))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es", classification="generic")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        assert "tree represents FUNCTION, not visual layout" in prompt

    async def test_prompt_mentions_overall_purpose_step(self):
        """The prompt includes the step to identify overall document purpose."""
        mock_client = _make_mock_llm_client(json.dumps(_valid_v2_response()))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es", classification="generic")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        assert "OVERALL PURPOSE" in prompt

    async def test_unknown_classification_defaults_to_generic_hint(self):
        """An unknown classification falls back to the generic purpose hint."""
        mock_client = _make_mock_llm_client(json.dumps(_valid_v2_response()))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es", classification="unknown_type")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        generic_hint = get_purpose_hint("generic")
        assert generic_hint in prompt


# --- Tests: IndexResult with functional_group and original_headings ---


class TestIndexResultV2Parsing:
    """Verify IndexResult correctly parses v2 fields."""

    async def test_functional_group_parsed_correctly(self):
        """IndexResult nodes include the functional_group field."""
        mock_client = _make_mock_llm_client(json.dumps(_valid_v2_response()))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(ir, language="es", classification="normative")

        result = response.result
        assert result.tree[0].functional_group == "purpose"
        assert result.tree[1].functional_group == "execution"
        assert result.tree[2].functional_group == "control"

    async def test_original_headings_parsed_correctly(self):
        """IndexResult nodes include the original_headings list."""
        mock_client = _make_mock_llm_client(json.dumps(_valid_v2_response()))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(ir, language="es", classification="normative")

        result = response.result
        assert result.tree[0].original_headings == ["Introducción", "Objetivo"]
        assert result.tree[1].original_headings == ["Uso de áreas comunes"]

    async def test_functional_group_defaults_to_none(self):
        """When functional_group is not provided, it defaults to None."""
        data = {
            "tree": [
                {
                    "id": "node-1",
                    "title": "General",
                    "level": 1,
                    "role": "defines",
                    "question_answered": "What is this?",
                    "source_ref": {
                        "chunk_ids": ["c1"],
                        "text_excerpt": "Some text.",
                        "section": "General",
                    },
                    "children": [],
                }
            ]
        }
        mock_client = _make_mock_llm_client(json.dumps(data))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(ir, language="es")

        assert response.result.tree[0].functional_group is None

    async def test_original_headings_defaults_to_empty_list(self):
        """When original_headings is not provided, it defaults to empty list."""
        data = {
            "tree": [
                {
                    "id": "node-1",
                    "title": "General",
                    "level": 1,
                    "role": "defines",
                    "question_answered": "What is this?",
                    "source_ref": {
                        "chunk_ids": ["c1"],
                        "text_excerpt": "Some text.",
                        "section": "General",
                    },
                    "children": [],
                }
            ]
        }
        mock_client = _make_mock_llm_client(json.dumps(data))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(ir, language="es")

        assert response.result.tree[0].original_headings == []


# --- Tests: document_purpose field ---


class TestDocumentPurpose:
    """Verify document_purpose field is present in results."""

    async def test_document_purpose_is_parsed(self):
        """IndexResult includes document_purpose from the LLM response."""
        mock_client = _make_mock_llm_client(json.dumps(_valid_v2_response()))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(ir, language="es", classification="normative")

        assert response.result.document_purpose is not None
        assert "coexistence rules" in response.result.document_purpose

    async def test_document_purpose_defaults_to_none(self):
        """When document_purpose is not in the response, it defaults to None."""
        data = {"tree": []}
        mock_client = _make_mock_llm_client(json.dumps(data))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(ir, language="es")

        assert response.result.document_purpose is None

    async def test_prompt_version_is_v2(self):
        """The analyzer returns prompt_version 'build-index-v2'."""
        mock_client = _make_mock_llm_client(json.dumps(_valid_v2_response()))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(ir, language="es")

        assert response.prompt_version == "build-index-v2"


# --- Tests: Role values include new vocabulary ---


class TestRoleNewVocabulary:
    """Verify that new role values (enables, restricts, controls, delegates) validate correctly."""

    def test_enables_role_validates(self):
        """The role 'enables' is accepted in StructureNode."""
        node = StructureNode(
            id="n1",
            title="Permissions",
            level=1,
            role="enables",
            question_answered="What is permitted?",
            source_ref=None,
            children=[],
        )
        assert node.role == "enables"

    def test_restricts_role_validates(self):
        """The role 'restricts' is accepted in StructureNode."""
        node = StructureNode(
            id="n2",
            title="Restrictions",
            level=1,
            role="restricts",
            question_answered="What is limited?",
            source_ref=None,
            children=[],
        )
        assert node.role == "restricts"

    def test_controls_role_validates(self):
        """The role 'controls' is accepted in StructureNode."""
        node = StructureNode(
            id="n3",
            title="Oversight",
            level=1,
            role="controls",
            question_answered="How is compliance checked?",
            source_ref=None,
            children=[],
        )
        assert node.role == "controls"

    def test_delegates_role_validates(self):
        """The role 'delegates' is accepted in StructureNode."""
        node = StructureNode(
            id="n4",
            title="Delegation",
            level=1,
            role="delegates",
            question_answered="Who is responsible?",
            source_ref=None,
            children=[],
        )
        assert node.role == "delegates"

    def test_role_normalized_to_lowercase(self):
        """Role values are normalized to lowercase."""
        node = StructureNode(
            id="n5",
            title="Test",
            level=1,
            role="ENABLES",
            question_answered=None,
            source_ref=None,
            children=[],
        )
        assert node.role == "enables"

    async def test_new_roles_in_full_analysis_response(self):
        """New role values are correctly parsed in a full analysis response."""
        data = {
            "document_purpose": "Regulate building usage",
            "tree": [
                {
                    "id": "node-1",
                    "title": "What residents can do",
                    "level": 1,
                    "role": "enables",
                    "functional_group": "permissions",
                    "original_headings": ["Chapter 3: Rights"],
                    "question_answered": "What actions are enabled for residents?",
                    "source_ref": {
                        "chunk_ids": ["c2"],
                        "text_excerpt": "Los residentes podrán usar las áreas comunes.",
                        "section": "Uso de áreas comunes",
                    },
                    "children": [
                        {
                            "id": "node-1.1",
                            "title": "Limitations on usage",
                            "level": 2,
                            "role": "restricts",
                            "functional_group": "permissions",
                            "original_headings": ["Sección 3.1: Restricciones"],
                            "question_answered": "What limits apply to common area usage?",
                            "source_ref": {
                                "chunk_ids": ["c2"],
                                "text_excerpt": "según horario",
                                "section": "Uso de áreas comunes",
                            },
                            "children": [],
                        }
                    ],
                },
                {
                    "id": "node-2",
                    "title": "Authority delegation",
                    "level": 1,
                    "role": "delegates",
                    "functional_group": "governance",
                    "original_headings": ["Chapter 5: Administración"],
                    "question_answered": "Who is delegated enforcement authority?",
                    "source_ref": {
                        "chunk_ids": ["c3"],
                        "text_excerpt": "El administrador controlará el cumplimiento.",
                        "section": "Control y fiscalización",
                    },
                    "children": [],
                },
            ],
        }
        mock_client = _make_mock_llm_client(json.dumps(data))
        analyzer = IndexAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(ir, language="es", classification="normative")

        assert response.result.tree[0].role == "enables"
        assert response.result.tree[0].children[0].role == "restricts"
        assert response.result.tree[1].role == "delegates"


# --- Tests: Purpose hint helper ---


class TestGetPurposeHint:
    """Test the get_purpose_hint helper function."""

    def test_normative_hint(self):
        hint = get_purpose_hint("normative")
        assert "rules" in hint or "obligations" in hint

    def test_procedure_hint(self):
        hint = get_purpose_hint("procedure")
        assert "steps" in hint or "workflows" in hint

    def test_narrative_hint(self):
        hint = get_purpose_hint("narrative")
        assert "story" in hint or "events" in hint or "sequence" in hint

    def test_generic_hint(self):
        hint = get_purpose_hint("generic")
        assert "information" in hint

    def test_unknown_falls_back_to_generic(self):
        hint = get_purpose_hint("completely_unknown_type")
        assert hint == get_purpose_hint("generic")
