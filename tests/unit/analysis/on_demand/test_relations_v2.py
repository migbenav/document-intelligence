"""Unit tests for Section Relations v2 — Functional Connections.

Validates v2-specific behavior of the RelationsAnalyzer and its prompt:
- Prompt includes classification
- Prompt excludes trivial relationships instruction
- New relation types (enables, restricts, requires, implements) validate correctly
- contradicts only flagged for same domain (prompt includes instruction)

Requirements covered: Req 4 (criteria 1-6)
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.analysis.llm_client import LLMResponse
from app.analysis.on_demand.models import (
    RelationsResult,
    SectionRelation,
)
from app.analysis.on_demand.relations_analyzer import RelationsAnalyzer
from app.analysis.on_demand.prompts.section_relations_v2 import (
    PROMPT_TEMPLATE,
    PROMPT_VERSION,
)
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    IntermediateRepresentation,
)


# --- Fixtures ---


def _make_ir() -> IntermediateRepresentation:
    """Build a minimal IR for testing."""
    chunks = [
        ContentChunkModel(
            chunk_id="c1",
            text="General policy for building access.",
            structural_context={"section": "Access Policy"},
            order=0,
        ),
        ContentChunkModel(
            chunk_id="c2",
            text="Procedures for granting access cards.",
            structural_context={"section": "Access Procedures"},
            order=1,
        ),
        ContentChunkModel(
            chunk_id="c3",
            text="Restrictions on visitor access hours.",
            structural_context={"section": "Visitor Restrictions"},
            order=2,
        ),
    ]
    return IntermediateRepresentation(
        document_id="doc-relations-v2",
        metadata=DocumentMetadata(
            original_filename="access_rules.md",
            format=DocumentFormat.MARKDOWN,
            size_bytes=2048,
            language=DetectedLanguage.SPANISH,
            upload_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ),
        chunks=chunks,
    )


def _make_mock_llm_client(response_content: str) -> MagicMock:
    """Create a mock LLMClient that returns the given content."""
    mock_client = MagicMock()
    mock_client.primary_model = "gemini/gemini-2.5-flash"
    mock_client.call = AsyncMock(
        return_value=LLMResponse(
            content=response_content, model_id="gemini/gemini-2.5-flash"
        )
    )
    return mock_client


# --- Test: Prompt includes classification ---


class TestPromptIncludesClassification:
    """Verify that the v2 prompt includes classification in the LLM call."""

    @pytest.mark.asyncio
    async def test_classification_appears_in_prompt(self):
        """The prompt sent to LLM contains 'This is a {classification} document.'"""
        mock_client = _make_mock_llm_client(json.dumps({"relations": []}))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es", classification="normative")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        assert "This is a normative document" in prompt

    @pytest.mark.asyncio
    async def test_procedure_classification_in_prompt(self):
        """Procedure classification is correctly interpolated."""
        mock_client = _make_mock_llm_client(json.dumps({"relations": []}))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="en", classification="procedure")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        assert "This is a procedure document" in prompt

    @pytest.mark.asyncio
    async def test_default_generic_classification(self):
        """Default classification is 'generic' when not specified."""
        mock_client = _make_mock_llm_client(json.dumps({"relations": []}))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        assert "This is a generic document" in prompt


# --- Test: Prompt excludes trivial relationships instruction ---


class TestPromptExcludesTrivialRelationships:
    """Verify the v2 prompt instructs LLM to exclude trivial relationships."""

    @pytest.mark.asyncio
    async def test_excludes_trivial_instruction_present(self):
        """The prompt contains instruction to EXCLUDE trivial relationships."""
        mock_client = _make_mock_llm_client(json.dumps({"relations": []}))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es", classification="normative")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        assert "EXCLUDE trivial relationships" in prompt

    def test_prompt_template_contains_trivial_exclusion(self):
        """The raw PROMPT_TEMPLATE contains the trivial exclusion instruction."""
        assert "EXCLUDE trivial relationships" in PROMPT_TEMPLATE
        # It should mention sequential order, adjacency as examples of trivial
        assert "sequential order" in PROMPT_TEMPLATE
        assert "adjacency" in PROMPT_TEMPLATE


# --- Test: New relation types validate correctly ---


class TestNewRelationTypesValidation:
    """Verify new v2 relation types (enables, restricts, requires, implements) validate."""

    @pytest.mark.asyncio
    async def test_enables_type_validates(self):
        """A relation with type 'enables' validates correctly."""
        data = {
            "relations": [
                {
                    "source_section": "Access Policy",
                    "target_section": "Access Procedures",
                    "type": "enables",
                    "description": "The policy enables the procedures.",
                    "domain": "access",
                    "source_ref": {
                        "chunk_ids": ["c1"],
                        "text_excerpt": "General policy for building access.",
                        "section": "Access Policy",
                    },
                }
            ]
        }
        mock_client = _make_mock_llm_client(json.dumps(data))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(ir, language="es")

        result = response.result
        assert isinstance(result, RelationsResult)
        assert result.relations[0].type == "enables"

    @pytest.mark.asyncio
    async def test_restricts_type_validates(self):
        """A relation with type 'restricts' validates correctly."""
        data = {
            "relations": [
                {
                    "source_section": "Visitor Restrictions",
                    "target_section": "Access Procedures",
                    "type": "restricts",
                    "description": "Visitor restrictions limit procedure scope.",
                    "domain": "access",
                    "source_ref": {
                        "chunk_ids": ["c3"],
                        "text_excerpt": "Restrictions on visitor access hours.",
                        "section": "Visitor Restrictions",
                    },
                }
            ]
        }
        mock_client = _make_mock_llm_client(json.dumps(data))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(ir, language="es")

        result = response.result
        assert isinstance(result, RelationsResult)
        assert result.relations[0].type == "restricts"

    @pytest.mark.asyncio
    async def test_requires_type_validates(self):
        """A relation with type 'requires' validates correctly."""
        data = {
            "relations": [
                {
                    "source_section": "Access Procedures",
                    "target_section": "Access Policy",
                    "type": "requires",
                    "description": "Procedures require an approved policy.",
                    "domain": "access",
                    "source_ref": {
                        "chunk_ids": ["c2"],
                        "text_excerpt": "Procedures for granting access cards.",
                        "section": "Access Procedures",
                    },
                }
            ]
        }
        mock_client = _make_mock_llm_client(json.dumps(data))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(ir, language="es")

        result = response.result
        assert isinstance(result, RelationsResult)
        assert result.relations[0].type == "requires"

    @pytest.mark.asyncio
    async def test_implements_type_validates(self):
        """A relation with type 'implements' validates correctly."""
        data = {
            "relations": [
                {
                    "source_section": "Access Procedures",
                    "target_section": "Access Policy",
                    "type": "implements",
                    "description": "Procedures implement the access policy.",
                    "domain": "access",
                    "source_ref": {
                        "chunk_ids": ["c2"],
                        "text_excerpt": "Procedures for granting access cards.",
                        "section": "Access Procedures",
                    },
                }
            ]
        }
        mock_client = _make_mock_llm_client(json.dumps(data))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(ir, language="es")

        result = response.result
        assert isinstance(result, RelationsResult)
        assert result.relations[0].type == "implements"

    @pytest.mark.asyncio
    async def test_contradicts_type_validates(self):
        """A relation with type 'contradicts' validates correctly."""
        data = {
            "relations": [
                {
                    "source_section": "Access Policy",
                    "target_section": "Visitor Restrictions",
                    "type": "contradicts",
                    "description": "Policy and restrictions conflict on hours.",
                    "domain": "access",
                    "source_ref": {
                        "chunk_ids": ["c1", "c3"],
                        "text_excerpt": "General policy for building access.",
                        "section": "Access Policy",
                    },
                }
            ]
        }
        mock_client = _make_mock_llm_client(json.dumps(data))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(ir, language="es")

        result = response.result
        assert isinstance(result, RelationsResult)
        assert result.relations[0].type == "contradicts"

    @pytest.mark.asyncio
    async def test_all_v2_types_in_single_response(self):
        """All five v2 relation types validate in a single response."""
        data = {
            "relations": [
                {
                    "source_section": "A",
                    "target_section": "B",
                    "type": "enables",
                    "description": "A enables B",
                    "domain": "test",
                    "source_ref": None,
                },
                {
                    "source_section": "B",
                    "target_section": "C",
                    "type": "restricts",
                    "description": "B restricts C",
                    "domain": "test",
                    "source_ref": None,
                },
                {
                    "source_section": "C",
                    "target_section": "D",
                    "type": "requires",
                    "description": "C requires D",
                    "domain": "test",
                    "source_ref": None,
                },
                {
                    "source_section": "D",
                    "target_section": "E",
                    "type": "implements",
                    "description": "D implements E",
                    "domain": "test",
                    "source_ref": None,
                },
                {
                    "source_section": "E",
                    "target_section": "F",
                    "type": "contradicts",
                    "description": "E contradicts F",
                    "domain": "test",
                    "source_ref": None,
                },
            ]
        }
        mock_client = _make_mock_llm_client(json.dumps(data))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(ir, language="es")

        result = response.result
        assert isinstance(result, RelationsResult)
        assert len(result.relations) == 5
        types = [r.type for r in result.relations]
        assert types == ["enables", "restricts", "requires", "implements", "contradicts"]

    def test_domain_field_on_section_relation(self):
        """SectionRelation model accepts domain field."""
        relation = SectionRelation(
            source_section="A",
            target_section="B",
            type="enables",
            description="A enables B",
            domain="parking",
            source_ref=None,
        )
        assert relation.domain == "parking"

    def test_domain_field_nullable(self):
        """SectionRelation model allows domain to be None."""
        relation = SectionRelation(
            source_section="A",
            target_section="B",
            type="restricts",
            description="A restricts B",
            domain=None,
            source_ref=None,
        )
        assert relation.domain is None


# --- Test: Contradicts only flagged for same domain ---


class TestContradictsSameDomainInstruction:
    """Verify prompt instructs that contradicts is only for same domain."""

    @pytest.mark.asyncio
    async def test_prompt_contains_same_domain_contradicts_instruction(self):
        """The prompt instructs that contradicts is ONLY within the SAME domain."""
        mock_client = _make_mock_llm_client(json.dumps({"relations": []}))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es", classification="normative")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        # The prompt must contain instruction about same domain for contradicts
        assert "SAME domain" in prompt or "same domain" in prompt.lower()

    @pytest.mark.asyncio
    async def test_prompt_forbids_cross_domain_contradictions(self):
        """The prompt explicitly says cross-domain contradictions are NOT valid."""
        mock_client = _make_mock_llm_client(json.dumps({"relations": []}))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        await analyzer.analyze(ir, language="es", classification="normative")

        call_args = mock_client.call.call_args
        prompt = call_args[0][0]
        # Check for the never cross-domain instruction
        assert "never cross-domain" in prompt.lower() or "NEVER" in prompt

    def test_prompt_template_contradicts_definition(self):
        """The PROMPT_TEMPLATE defines contradicts as same-domain only."""
        # Check the contradicts definition in the template
        assert "contradicts" in PROMPT_TEMPLATE
        assert "SAME domain" in PROMPT_TEMPLATE
        # Explicitly mentions never cross-domain
        assert "never cross-domain" in PROMPT_TEMPLATE

    def test_prompt_template_uses_domain_example(self):
        """The PROMPT_TEMPLATE mentions concrete cross-domain example (parking vs elevators)."""
        # The prompt mentions parking rules vs elevator rules as an example
        # of things that are different domains (from the design doc)
        assert "different domains" in PROMPT_TEMPLATE or "SAME topic/domain" in PROMPT_TEMPLATE


# --- Test: Prompt version is v2 ---


class TestPromptVersion:
    """Verify the prompt version is correctly set to v2."""

    def test_prompt_version_constant(self):
        """The PROMPT_VERSION constant is 'section-relations-v2'."""
        assert PROMPT_VERSION == "section-relations-v2"

    @pytest.mark.asyncio
    async def test_analyzer_returns_v2_prompt_version(self):
        """The AnalyzerResponse includes the v2 prompt version."""
        mock_client = _make_mock_llm_client(json.dumps({"relations": []}))
        analyzer = RelationsAnalyzer(mock_client)
        ir = _make_ir()

        response = await analyzer.analyze(ir, language="es")

        assert response.prompt_version == "section-relations-v2"
