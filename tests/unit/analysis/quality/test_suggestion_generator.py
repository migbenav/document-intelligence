"""Unit tests for SuggestionGenerator.

Covers:
- Suggestions generated from findings
- Max 20 suggestions enforced (Req 4.6)
- High-severity coverage (Req 4.4)
- Empty findings empty result (Req 4.5)
- Source_refs present on all suggestions (Req 7.6)

Requirements validated: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 7.6
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.analysis.llm_client import LLMClient, LLMResponse
from app.analysis.quality.suggestion_generator import SuggestionGenerator
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    IntermediateRepresentation,
)
from app.models.knowledge_model import (
    ExtractionMetadata,
    KnowledgeElement,
    KnowledgeModel,
    SourceRef,
)
from app.models.quality_analysis import (
    FindingSourceRef,
    Inconsistency,
    MissingElement,
    Suggestion,
)
from datetime import datetime


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_llm_client() -> LLMClient:
    """Create a mock LLM client."""
    client = MagicMock(spec=LLMClient)
    client.call = AsyncMock()
    return client


@pytest.fixture
def sample_ir() -> IntermediateRepresentation:
    """Create a sample IR with chunks."""
    return IntermediateRepresentation(
        document_id="doc-001",
        metadata=DocumentMetadata(
            original_filename="test.md",
            format=DocumentFormat.MARKDOWN,
            size_bytes=1024,
            language=DetectedLanguage.ENGLISH,
            upload_timestamp=datetime(2024, 1, 1),
        ),
        chunks=[
            ContentChunkModel(
                chunk_id="chunk-001",
                text="The system requires user authentication via OAuth2.",
                structural_context={"section": "## Authentication"},
                order=0,
            ),
            ContentChunkModel(
                chunk_id="chunk-002",
                text="Performance requirements: all endpoints must respond within 200ms.",
                structural_context={"section": "## Performance"},
                order=1,
            ),
        ],
    )


@pytest.fixture
def sample_km() -> KnowledgeModel:
    """Create a sample Knowledge Model."""
    return KnowledgeModel(
        document_id="doc-001",
        document_type="prd",
        elements=[
            KnowledgeElement(
                id="elem-001",
                type="concepto",
                name="Authentication",
                content="OAuth2-based user authentication",
                source_ref=SourceRef(
                    document_id="doc-001",
                    chunk_id="chunk-001",
                    section="## Authentication",
                    evidence="The system requires user authentication via OAuth2.",
                ),
                verified=True,
            ),
        ],
        extraction_metadata=ExtractionMetadata(
            prompt_version="extraction-v1",
            model_id="gemini/gemini-2.5-flash-preview-05-20",
            temperature=0.1,
            element_count=1,
            relationship_count=0,
            verification_rate=1.0,
            extracted_at=datetime(2024, 1, 1),
        ),
    )


@pytest.fixture
def high_severity_inconsistency() -> Inconsistency:
    """Create a high-severity inconsistency."""
    return Inconsistency(
        id="inc-001",
        type="contradiction",
        description="Section 3 says 200ms, Section 5 says 500ms for same endpoint.",
        severity="high",
        affected_element_ids=["elem-001", "elem-002"],
        source_refs=[
            FindingSourceRef(
                document_id="doc-001",
                chunk_id="chunk-001",
                evidence="Response time: 200ms",
            ),
            FindingSourceRef(
                document_id="doc-001",
                chunk_id="chunk-002",
                evidence="Response time: 500ms",
            ),
        ],
    )


@pytest.fixture
def high_severity_missing() -> MissingElement:
    """Create a high-severity missing element."""
    return MissingElement(
        id="miss-001",
        classification="missing",
        expected_element="criterios de éxito",
        description="PRD should define measurable success criteria.",
        severity="high",
        schema_reference="prd",
    )


@pytest.fixture
def low_severity_inconsistency() -> Inconsistency:
    """Create a low-severity inconsistency."""
    return Inconsistency(
        id="inc-002",
        type="ambiguity",
        description="The term 'quickly' is vague.",
        severity="low",
        affected_element_ids=["elem-003"],
        source_refs=[
            FindingSourceRef(
                document_id="doc-001",
                chunk_id="chunk-001",
                evidence="System must respond quickly.",
            ),
        ],
    )


def _make_llm_response(suggestions: list[dict]) -> LLMResponse:
    """Build an LLM response with the given suggestions JSON."""
    return LLMResponse(
        content=json.dumps({"suggestions": suggestions}),
        model_id="gemini/gemini-2.5-flash-preview-05-20",
    )


def _make_suggestion_data(
    id: str = "sug-001",
    description: str = "Add explicit response time SLA with specific values.",
    category: str = "consistency",
    priority: str = "high",
    related_finding_ids: list[str] | None = None,
    chunk_id: str = "chunk-001",
    evidence: str = "Response time: 200ms",
) -> dict:
    """Helper to build a suggestion dict matching LLM response format."""
    return {
        "id": id,
        "description": description,
        "category": category,
        "priority": priority,
        "related_finding_ids": related_finding_ids or [],
        "source_refs": [
            {
                "chunk_id": chunk_id,
                "page": None,
                "section": "## Performance",
                "evidence": evidence,
            }
        ],
    }


# =============================================================================
# Tests: Suggestions Generated from Findings
# =============================================================================


class TestSuggestionsGenerated:
    """Tests that suggestions are correctly generated from findings."""

    @pytest.mark.asyncio
    async def test_generates_suggestions_from_inconsistencies(
        self,
        mock_llm_client: LLMClient,
        sample_ir: IntermediateRepresentation,
        sample_km: KnowledgeModel,
        high_severity_inconsistency: Inconsistency,
    ):
        """Generator produces suggestions when inconsistencies exist."""
        mock_llm_client.call.return_value = _make_llm_response(
            [_make_suggestion_data(related_finding_ids=["inc-001"])]
        )

        generator = SuggestionGenerator(mock_llm_client)
        result = await generator.generate(
            [high_severity_inconsistency], [], sample_km, sample_ir
        )

        assert len(result) == 1
        assert result[0].id == "sug-001"
        assert result[0].category == "consistency"
        assert result[0].priority == "high"
        assert "inc-001" in result[0].related_finding_ids

    @pytest.mark.asyncio
    async def test_generates_suggestions_from_missing_elements(
        self,
        mock_llm_client: LLMClient,
        sample_ir: IntermediateRepresentation,
        sample_km: KnowledgeModel,
        high_severity_missing: MissingElement,
    ):
        """Generator produces suggestions when missing elements exist."""
        mock_llm_client.call.return_value = _make_llm_response(
            [
                _make_suggestion_data(
                    id="sug-002",
                    description="Add a section defining measurable success criteria with specific KPIs.",
                    category="completeness",
                    priority="high",
                    related_finding_ids=["miss-001"],
                )
            ]
        )

        generator = SuggestionGenerator(mock_llm_client)
        result = await generator.generate(
            [], [high_severity_missing], sample_km, sample_ir
        )

        assert len(result) == 1
        assert result[0].category == "completeness"
        assert "miss-001" in result[0].related_finding_ids

    @pytest.mark.asyncio
    async def test_calls_llm_with_primary_model_and_low_temperature(
        self,
        mock_llm_client: LLMClient,
        sample_ir: IntermediateRepresentation,
        sample_km: KnowledgeModel,
        high_severity_inconsistency: Inconsistency,
    ):
        """Generator calls LLM with primary model tier and temperature 0.1."""
        mock_llm_client.call.return_value = _make_llm_response(
            [_make_suggestion_data(related_finding_ids=["inc-001"])]
        )

        generator = SuggestionGenerator(mock_llm_client)
        await generator.generate(
            [high_severity_inconsistency], [], sample_km, sample_ir
        )

        mock_llm_client.call.assert_called_once()
        call_kwargs = mock_llm_client.call.call_args
        assert call_kwargs.kwargs["model_tier"] == "primary"
        assert call_kwargs.kwargs["temperature"] == 0.1

    @pytest.mark.asyncio
    async def test_raises_on_invalid_json(
        self,
        mock_llm_client: LLMClient,
        sample_ir: IntermediateRepresentation,
        sample_km: KnowledgeModel,
        high_severity_inconsistency: Inconsistency,
    ):
        """Generator raises ValueError when LLM returns invalid JSON."""
        mock_llm_client.call.return_value = LLMResponse(
            content="not valid json {{{",
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        generator = SuggestionGenerator(mock_llm_client)
        with pytest.raises(ValueError, match="not valid JSON"):
            await generator.generate(
                [high_severity_inconsistency], [], sample_km, sample_ir
            )

    @pytest.mark.asyncio
    async def test_raises_on_missing_suggestions_key(
        self,
        mock_llm_client: LLMClient,
        sample_ir: IntermediateRepresentation,
        sample_km: KnowledgeModel,
        high_severity_inconsistency: Inconsistency,
    ):
        """Generator raises ValueError when JSON lacks 'suggestions' key."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"results": []}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        generator = SuggestionGenerator(mock_llm_client)
        with pytest.raises(ValueError, match="missing 'suggestions' key"):
            await generator.generate(
                [high_severity_inconsistency], [], sample_km, sample_ir
            )

    @pytest.mark.asyncio
    async def test_handles_markdown_code_fences_in_response(
        self,
        mock_llm_client: LLMClient,
        sample_ir: IntermediateRepresentation,
        sample_km: KnowledgeModel,
        high_severity_inconsistency: Inconsistency,
    ):
        """Generator strips markdown code fences from LLM response."""
        content = json.dumps(
            {"suggestions": [_make_suggestion_data(related_finding_ids=["inc-001"])]}
        )
        wrapped = f"```json\n{content}\n```"
        mock_llm_client.call.return_value = LLMResponse(
            content=wrapped,
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        generator = SuggestionGenerator(mock_llm_client)
        result = await generator.generate(
            [high_severity_inconsistency], [], sample_km, sample_ir
        )

        assert len(result) == 1
        assert result[0].id == "sug-001"


# =============================================================================
# Tests: Max 20 Suggestions Enforced (Req 4.6)
# =============================================================================


class TestMaxSuggestionsEnforced:
    """Tests that no more than 20 suggestions are returned."""

    @pytest.mark.asyncio
    async def test_truncates_to_20_suggestions(
        self,
        mock_llm_client: LLMClient,
        sample_ir: IntermediateRepresentation,
        sample_km: KnowledgeModel,
        high_severity_inconsistency: Inconsistency,
    ):
        """When LLM returns more than 20 suggestions, result is capped at 20."""
        # Generate 25 suggestions
        suggestions_data = [
            _make_suggestion_data(
                id=f"sug-{i:03d}",
                description=f"Suggestion number {i}",
                priority="medium",
                related_finding_ids=["inc-001"] if i == 0 else [],
            )
            for i in range(25)
        ]
        mock_llm_client.call.return_value = _make_llm_response(suggestions_data)

        generator = SuggestionGenerator(mock_llm_client)
        result = await generator.generate(
            [high_severity_inconsistency], [], sample_km, sample_ir
        )

        assert len(result) <= 20

    @pytest.mark.asyncio
    async def test_truncates_lowest_priority_first(
        self,
        mock_llm_client: LLMClient,
        sample_ir: IntermediateRepresentation,
        sample_km: KnowledgeModel,
        high_severity_inconsistency: Inconsistency,
    ):
        """Truncation removes low-priority suggestions before higher ones."""
        # 10 high, 10 medium, 5 low = 25 total
        suggestions_data = []
        for i in range(10):
            suggestions_data.append(
                _make_suggestion_data(
                    id=f"sug-h-{i}",
                    priority="high",
                    related_finding_ids=["inc-001"] if i == 0 else [],
                )
            )
        for i in range(10):
            suggestions_data.append(
                _make_suggestion_data(id=f"sug-m-{i}", priority="medium")
            )
        for i in range(5):
            suggestions_data.append(
                _make_suggestion_data(id=f"sug-l-{i}", priority="low")
            )

        mock_llm_client.call.return_value = _make_llm_response(suggestions_data)

        generator = SuggestionGenerator(mock_llm_client)
        result = await generator.generate(
            [high_severity_inconsistency], [], sample_km, sample_ir
        )

        assert len(result) == 20
        # All high-priority suggestions should be kept
        high_count = sum(1 for s in result if s.priority == "high")
        assert high_count == 10
        # All medium-priority suggestions should be kept
        medium_count = sum(1 for s in result if s.priority == "medium")
        assert medium_count == 10
        # Low-priority suggestions should be removed
        low_count = sum(1 for s in result if s.priority == "low")
        assert low_count == 0

    @pytest.mark.asyncio
    async def test_exactly_20_not_truncated(
        self,
        mock_llm_client: LLMClient,
        sample_ir: IntermediateRepresentation,
        sample_km: KnowledgeModel,
        high_severity_inconsistency: Inconsistency,
    ):
        """Exactly 20 suggestions are returned without truncation."""
        suggestions_data = [
            _make_suggestion_data(
                id=f"sug-{i:03d}",
                priority="medium",
                related_finding_ids=["inc-001"] if i == 0 else [],
            )
            for i in range(20)
        ]
        mock_llm_client.call.return_value = _make_llm_response(suggestions_data)

        generator = SuggestionGenerator(mock_llm_client)
        result = await generator.generate(
            [high_severity_inconsistency], [], sample_km, sample_ir
        )

        assert len(result) == 20


# =============================================================================
# Tests: High-Severity Coverage (Req 4.4)
# =============================================================================


class TestHighSeverityCoverage:
    """Tests that at least one suggestion is generated per high-severity finding."""

    @pytest.mark.asyncio
    async def test_generates_placeholder_for_uncovered_high_severity(
        self,
        mock_llm_client: LLMClient,
        sample_ir: IntermediateRepresentation,
        sample_km: KnowledgeModel,
        high_severity_inconsistency: Inconsistency,
    ):
        """If LLM omits a high-severity finding, a placeholder is generated."""
        # LLM returns a suggestion that doesn't reference the high-severity finding
        mock_llm_client.call.return_value = _make_llm_response(
            [_make_suggestion_data(id="sug-001", priority="low", related_finding_ids=[])]
        )

        generator = SuggestionGenerator(mock_llm_client)
        result = await generator.generate(
            [high_severity_inconsistency], [], sample_km, sample_ir
        )

        # Should have at least one suggestion referencing inc-001
        high_severity_covered = any(
            "inc-001" in s.related_finding_ids for s in result
        )
        assert high_severity_covered

    @pytest.mark.asyncio
    async def test_multiple_high_severity_findings_all_covered(
        self,
        mock_llm_client: LLMClient,
        sample_ir: IntermediateRepresentation,
        sample_km: KnowledgeModel,
        high_severity_inconsistency: Inconsistency,
        high_severity_missing: MissingElement,
    ):
        """All high-severity findings get at least one suggestion."""
        # LLM returns nothing related to these findings
        mock_llm_client.call.return_value = _make_llm_response(
            [_make_suggestion_data(id="sug-001", priority="low", related_finding_ids=[])]
        )

        generator = SuggestionGenerator(mock_llm_client)
        result = await generator.generate(
            [high_severity_inconsistency],
            [high_severity_missing],
            sample_km,
            sample_ir,
        )

        # Both high-severity findings should be covered
        covered_finding_ids = set()
        for s in result:
            covered_finding_ids.update(s.related_finding_ids)
        assert "inc-001" in covered_finding_ids
        assert "miss-001" in covered_finding_ids

    @pytest.mark.asyncio
    async def test_no_placeholder_when_already_covered(
        self,
        mock_llm_client: LLMClient,
        sample_ir: IntermediateRepresentation,
        sample_km: KnowledgeModel,
        high_severity_inconsistency: Inconsistency,
    ):
        """No placeholder if LLM already references the high-severity finding."""
        mock_llm_client.call.return_value = _make_llm_response(
            [
                _make_suggestion_data(
                    id="sug-001", priority="high", related_finding_ids=["inc-001"]
                )
            ]
        )

        generator = SuggestionGenerator(mock_llm_client)
        result = await generator.generate(
            [high_severity_inconsistency], [], sample_km, sample_ir
        )

        # Only 1 suggestion — no placeholder added
        assert len(result) == 1
        assert result[0].id == "sug-001"


# =============================================================================
# Tests: Empty Findings Empty Result (Req 4.5)
# =============================================================================


class TestEmptyFindingsEmptyResult:
    """Tests that zero findings + no structural improvements = empty result."""

    @pytest.mark.asyncio
    async def test_empty_list_when_no_findings_no_suggestions(
        self,
        mock_llm_client: LLMClient,
        sample_ir: IntermediateRepresentation,
        sample_km: KnowledgeModel,
    ):
        """Returns empty list when no findings exist and LLM returns nothing."""
        mock_llm_client.call.return_value = _make_llm_response([])

        generator = SuggestionGenerator(mock_llm_client)
        result = await generator.generate([], [], sample_km, sample_ir)

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_suggestions_when_no_findings_but_structural_improvements(
        self,
        mock_llm_client: LLMClient,
        sample_ir: IntermediateRepresentation,
        sample_km: KnowledgeModel,
    ):
        """Returns suggestions when no findings but LLM identifies structural improvements."""
        mock_llm_client.call.return_value = _make_llm_response(
            [
                _make_suggestion_data(
                    id="sug-001",
                    description="Reorganize sections for better readability.",
                    category="structure",
                    priority="low",
                )
            ]
        )

        generator = SuggestionGenerator(mock_llm_client)
        result = await generator.generate([], [], sample_km, sample_ir)

        assert len(result) == 1
        assert result[0].category == "structure"


# =============================================================================
# Tests: Source_refs Present (Req 7.6)
# =============================================================================


class TestSourceRefsPresent:
    """Tests that every suggestion has at least one source_ref."""

    @pytest.mark.asyncio
    async def test_all_suggestions_have_source_refs(
        self,
        mock_llm_client: LLMClient,
        sample_ir: IntermediateRepresentation,
        sample_km: KnowledgeModel,
        high_severity_inconsistency: Inconsistency,
    ):
        """Every suggestion in the output has at least one source_ref."""
        mock_llm_client.call.return_value = _make_llm_response(
            [
                _make_suggestion_data(
                    id="sug-001",
                    priority="high",
                    related_finding_ids=["inc-001"],
                ),
                _make_suggestion_data(
                    id="sug-002",
                    priority="medium",
                ),
            ]
        )

        generator = SuggestionGenerator(mock_llm_client)
        result = await generator.generate(
            [high_severity_inconsistency], [], sample_km, sample_ir
        )

        for suggestion in result:
            assert len(suggestion.source_refs) >= 1, (
                f"Suggestion {suggestion.id} has no source_refs"
            )

    @pytest.mark.asyncio
    async def test_adds_fallback_source_ref_when_missing(
        self,
        mock_llm_client: LLMClient,
        sample_ir: IntermediateRepresentation,
        sample_km: KnowledgeModel,
        high_severity_inconsistency: Inconsistency,
    ):
        """Adds a fallback source_ref when LLM omits it from a suggestion."""
        # Suggestion without source_refs from LLM
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps(
                {
                    "suggestions": [
                        {
                            "id": "sug-001",
                            "description": "Improve structure.",
                            "category": "structure",
                            "priority": "high",
                            "related_finding_ids": ["inc-001"],
                            "source_refs": [],
                        }
                    ]
                }
            ),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        generator = SuggestionGenerator(mock_llm_client)
        result = await generator.generate(
            [high_severity_inconsistency], [], sample_km, sample_ir
        )

        assert len(result[0].source_refs) >= 1
        # Fallback should reference the first IR chunk
        assert result[0].source_refs[0].chunk_id == "chunk-001"

    @pytest.mark.asyncio
    async def test_source_refs_have_document_id(
        self,
        mock_llm_client: LLMClient,
        sample_ir: IntermediateRepresentation,
        sample_km: KnowledgeModel,
        high_severity_inconsistency: Inconsistency,
    ):
        """All source_refs include the correct document_id from the IR."""
        mock_llm_client.call.return_value = _make_llm_response(
            [_make_suggestion_data(related_finding_ids=["inc-001"])]
        )

        generator = SuggestionGenerator(mock_llm_client)
        result = await generator.generate(
            [high_severity_inconsistency], [], sample_km, sample_ir
        )

        for suggestion in result:
            for ref in suggestion.source_refs:
                assert ref.document_id == "doc-001"

    @pytest.mark.asyncio
    async def test_placeholder_suggestions_have_source_refs(
        self,
        mock_llm_client: LLMClient,
        sample_ir: IntermediateRepresentation,
        sample_km: KnowledgeModel,
        high_severity_inconsistency: Inconsistency,
    ):
        """Placeholder suggestions for uncovered findings also have source_refs."""
        # LLM returns no suggestions at all — placeholder needed
        mock_llm_client.call.return_value = _make_llm_response([])

        generator = SuggestionGenerator(mock_llm_client)
        result = await generator.generate(
            [high_severity_inconsistency], [], sample_km, sample_ir
        )

        # Should have a placeholder for high-severity finding
        assert len(result) >= 1
        for suggestion in result:
            assert len(suggestion.source_refs) >= 1
