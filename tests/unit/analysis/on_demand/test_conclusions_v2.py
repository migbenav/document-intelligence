"""Unit tests for Conclusions v2 prompt and model changes.

Tests v2-specific behavior:
- Prompt includes classification and domain identification step
- Prompt explicitly forbids cross-domain contradictions
- ConclusionsResult with domains_identified parses correctly
- New categories validate correctly

Requirements: Req 3 (criteria 1-10)
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.analysis.llm_client import LLMClient, LLMResponse
from app.analysis.on_demand.conclusions_analyzer import (
    ALLOWED_CATEGORIES,
    ConclusionsAnalyzer,
)
from app.analysis.on_demand.models import ConclusionsResult, Observation
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentMetadata,
    IntermediateRepresentation,
)


# --- Fixtures ---


@pytest.fixture
def mock_llm_client():
    """Create a mock LLMClient."""
    client = MagicMock(spec=LLMClient)
    client.call = AsyncMock()
    client.primary_model = "gemini/gemini-2.5-flash"
    return client


@pytest.fixture
def sample_ir():
    """Create a sample IntermediateRepresentation for testing."""
    return IntermediateRepresentation(
        document_id="doc-v2-001",
        metadata=DocumentMetadata(
            original_filename="reglamento.md",
            format="markdown",
            size_bytes=2048,
            language=DetectedLanguage.SPANISH,
            upload_timestamp="2026-07-26T15:00:00Z",
        ),
        chunks=[
            ContentChunkModel(
                chunk_id="c1",
                text="Las normas de estacionamiento establecen horarios y sanciones.",
                structural_context={"section": "Estacionamiento"},
                order=0,
            ),
            ContentChunkModel(
                chunk_id="c2",
                text="El uso de ascensores se limita a residentes y personal autorizado.",
                structural_context={"section": "Ascensores"},
                order=1,
            ),
            ContentChunkModel(
                chunk_id="c3",
                text="Las áreas comunes deben mantenerse limpias por todos los residentes.",
                structural_context={"section": "Áreas Comunes"},
                order=2,
            ),
        ],
    )


@pytest.fixture
def valid_v2_response():
    """A valid v2 conclusions response with domains_identified."""
    return {
        "domains_identified": ["estacionamiento", "ascensores", "áreas comunes"],
        "observations": [
            {
                "category": "sequence_issue",
                "description": "Parking sanctions are defined before the rules they enforce.",
                "suggestion": "Mover la sección de sanciones después de las reglas de estacionamiento.",
                "section_ref": "Estacionamiento",
                "domain": "estacionamiento",
                "source_ref": {
                    "chunk_ids": ["c1"],
                    "text_excerpt": "Las normas de estacionamiento establecen horarios y sanciones.",
                    "section": "Estacionamiento",
                },
            },
            {
                "category": "title_mismatch",
                "description": "The 'Áreas Comunes' heading contains rules about maintenance responsibilities, not just common areas.",
                "suggestion": "Renombrar la sección a 'Mantenimiento de Áreas Comunes'.",
                "section_ref": "Áreas Comunes",
                "domain": "áreas comunes",
                "source_ref": {
                    "chunk_ids": ["c3"],
                    "text_excerpt": "Las áreas comunes deben mantenerse limpias por todos los residentes.",
                    "section": "Áreas Comunes",
                },
            },
        ],
    }


# --- Tests: Prompt includes classification and domain identification step ---


class TestConclusionsV2PromptClassification:
    """Tests that the v2 prompt includes classification and domain identification."""

    @pytest.mark.asyncio
    async def test_prompt_includes_classification(
        self, mock_llm_client, sample_ir, valid_v2_response
    ):
        """Prompt contains the classification value passed to the analyzer."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps(valid_v2_response),
            model_id="gemini/gemini-2.5-flash",
        )

        analyzer = ConclusionsAnalyzer(mock_llm_client)
        await analyzer.analyze(
            sample_ir,
            language="en",
            document_language="es",
            classification="normative",
        )

        call_args = mock_llm_client.call.call_args
        prompt = call_args[0][0]
        assert "normative" in prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_domain_identification_step(
        self, mock_llm_client, sample_ir, valid_v2_response
    ):
        """Prompt instructs the LLM to identify independent domains/topics."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps(valid_v2_response),
            model_id="gemini/gemini-2.5-flash",
        )

        analyzer = ConclusionsAnalyzer(mock_llm_client)
        await analyzer.analyze(
            sample_ir,
            language="en",
            document_language="es",
            classification="normative",
        )

        call_args = mock_llm_client.call.call_args
        prompt = call_args[0][0]
        # The prompt should contain the domain identification step
        assert "INDEPENDENT DOMAINS" in prompt or "DOMAINS/TOPICS" in prompt

    @pytest.mark.asyncio
    async def test_prompt_default_classification_is_generic(
        self, mock_llm_client, sample_ir, valid_v2_response
    ):
        """When no classification is provided, the prompt uses 'generic'."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps(valid_v2_response),
            model_id="gemini/gemini-2.5-flash",
        )

        analyzer = ConclusionsAnalyzer(mock_llm_client)
        await analyzer.analyze(
            sample_ir,
            language="en",
            document_language="es",
            # classification defaults to "generic"
        )

        call_args = mock_llm_client.call.call_args
        prompt = call_args[0][0]
        assert "generic" in prompt


# --- Tests: Prompt explicitly forbids cross-domain contradictions ---


class TestConclusionsV2CrossDomainForbidden:
    """Tests that the v2 prompt forbids cross-domain contradictions."""

    @pytest.mark.asyncio
    async def test_prompt_forbids_cross_domain_contradictions(
        self, mock_llm_client, sample_ir, valid_v2_response
    ):
        """Prompt contains explicit instruction to NEVER flag cross-domain contradictions."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps(valid_v2_response),
            model_id="gemini/gemini-2.5-flash",
        )

        analyzer = ConclusionsAnalyzer(mock_llm_client)
        await analyzer.analyze(
            sample_ir,
            language="en",
            document_language="es",
            classification="normative",
        )

        call_args = mock_llm_client.call.call_args
        prompt = call_args[0][0]
        # The prompt must explicitly state not to flag cross-domain contradictions
        assert "NEVER" in prompt
        assert "contradictions between INDEPENDENT domains" in prompt or \
               "contradictions between independent domains" in prompt.lower()

    @pytest.mark.asyncio
    async def test_prompt_mentions_same_domain_for_contradictions(
        self, mock_llm_client, sample_ir, valid_v2_response
    ):
        """Prompt states contradictions are only valid within the SAME domain."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps(valid_v2_response),
            model_id="gemini/gemini-2.5-flash",
        )

        analyzer = ConclusionsAnalyzer(mock_llm_client)
        await analyzer.analyze(
            sample_ir,
            language="en",
            document_language="es",
            classification="normative",
        )

        call_args = mock_llm_client.call.call_args
        prompt = call_args[0][0]
        # Prompt should make clear contradictions are only within the same domain
        assert "SAME domain" in prompt or "same domain" in prompt.lower()


# --- Tests: ConclusionsResult with domains_identified parses correctly ---


class TestConclusionsV2DomainsIdentified:
    """Tests that ConclusionsResult with domains_identified parses correctly."""

    def test_conclusions_result_with_domains_identified(self):
        """ConclusionsResult parses domains_identified list."""
        data = {
            "observations": [
                {
                    "category": "duplication",
                    "description": "Duplicated content about parking.",
                    "suggestion": "Unificar las secciones duplicadas.",
                    "section_ref": "Estacionamiento",
                    "domain": "estacionamiento",
                    "source_ref": {
                        "chunk_ids": ["c1"],
                        "text_excerpt": "text",
                        "section": "Estacionamiento",
                    },
                }
            ],
            "domains_identified": ["estacionamiento", "ascensores", "áreas comunes"],
        }
        result = ConclusionsResult.model_validate(data)
        assert result.domains_identified == ["estacionamiento", "ascensores", "áreas comunes"]
        assert len(result.observations) == 1

    def test_conclusions_result_empty_domains_identified(self):
        """ConclusionsResult defaults to empty list when domains_identified is absent."""
        data = {
            "observations": [],
        }
        result = ConclusionsResult.model_validate(data)
        assert result.domains_identified == []

    def test_observation_with_domain_field(self):
        """Observation model accepts and stores the domain field."""
        data = {
            "category": "contradiction",
            "description": "Conflicting parking rules within the same domain.",
            "suggestion": "Resolver la contradicción entre las reglas.",
            "section_ref": "Estacionamiento - Sanciones",
            "domain": "estacionamiento",
            "source_ref": {
                "chunk_ids": ["c1"],
                "text_excerpt": "text excerpt",
                "section": "Estacionamiento",
            },
        }
        obs = Observation.model_validate(data)
        assert obs.domain == "estacionamiento"
        assert obs.category == "contradiction"

    def test_observation_domain_can_be_none(self):
        """Observation model accepts domain=None for document-level observations."""
        data = {
            "category": "purpose_mismatch",
            "description": "General purpose mismatch.",
            "suggestion": "Reorganizar el documento.",
            "section_ref": None,
            "domain": None,
            "source_ref": {
                "chunk_ids": ["c1"],
                "text_excerpt": "text",
                "section": "Intro",
            },
        }
        obs = Observation.model_validate(data)
        assert obs.domain is None

    @pytest.mark.asyncio
    async def test_analyzer_returns_domains_identified(
        self, mock_llm_client, sample_ir, valid_v2_response
    ):
        """Analyzer correctly returns domains_identified from LLM response."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps(valid_v2_response),
            model_id="gemini/gemini-2.5-flash",
        )

        analyzer = ConclusionsAnalyzer(mock_llm_client)
        response = await analyzer.analyze(
            sample_ir,
            language="en",
            document_language="es",
            classification="normative",
        )

        result = response.result
        assert isinstance(result, ConclusionsResult)
        assert result.domains_identified == ["estacionamiento", "ascensores", "áreas comunes"]


# --- Tests: New categories validate correctly ---


class TestConclusionsV2Categories:
    """Tests that new v2 categories validate correctly."""

    @pytest.mark.parametrize(
        "category",
        [
            "purpose_mismatch",
            "misplaced_content",
            "title_mismatch",
            "sequence_issue",
            "duplication",
            "contradiction",
        ],
    )
    def test_each_v2_category_validates(self, category):
        """Each of the six v2 categories validates correctly in Observation model."""
        data = {
            "category": category,
            "description": f"Test observation for {category}",
            "suggestion": "Structural suggestion",
            "section_ref": "Some Section",
            "domain": "test_domain",
            "source_ref": {
                "chunk_ids": ["c1"],
                "text_excerpt": "excerpt",
                "section": "Section",
            },
        }
        obs = Observation.model_validate(data)
        assert obs.category == category

    def test_allowed_categories_has_six_entries(self):
        """ALLOWED_CATEGORIES has exactly 6 categories per the v2 spec."""
        assert len(ALLOWED_CATEGORIES) == 6

    def test_allowed_categories_content(self):
        """ALLOWED_CATEGORIES contains exactly the v2 categories."""
        expected = {
            "purpose_mismatch",
            "misplaced_content",
            "title_mismatch",
            "sequence_issue",
            "duplication",
            "contradiction",
        }
        assert ALLOWED_CATEGORIES == expected

    @pytest.mark.asyncio
    async def test_invalid_category_corrected_to_purpose_mismatch(
        self, mock_llm_client, sample_ir
    ):
        """Invalid categories from LLM are corrected to purpose_mismatch."""
        data = {
            "domains_identified": ["general"],
            "observations": [
                {
                    "category": "readability",  # Not a valid v2 category
                    "description": "Readability issue",
                    "suggestion": "Reescribir para mayor claridad.",
                    "section_ref": "Intro",
                    "domain": "general",
                    "source_ref": {
                        "chunk_ids": ["c1"],
                        "text_excerpt": "text",
                        "section": "Intro",
                    },
                }
            ],
        }
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps(data),
            model_id="gemini/gemini-2.5-flash",
        )

        analyzer = ConclusionsAnalyzer(mock_llm_client)
        response = await analyzer.analyze(
            sample_ir,
            language="en",
            document_language="es",
            classification="generic",
        )

        assert response.result.observations[0].category == "purpose_mismatch"
