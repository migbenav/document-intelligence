"""Unit tests for the ContextBuilder module.

Covers: element selection with mocked LLM scoring, max 20 element cap,
one-hop relational context, 60% token budget enforcement, priority ordering,
fallback on scoring failure, None return for no relevant elements,
and unverified element annotation.

Requirements covered: 2.1, 2.2, 2.4, 2.5, 2.7
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.analysis.llm_client import LLMResponse

pytestmark = pytest.mark.asyncio
from app.analysis.query.context_builder import ContextBuilder
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
    Relation,
    SourceRef,
)


# --- Fixtures ---


@pytest.fixture
def sample_metadata() -> DocumentMetadata:
    return DocumentMetadata(
        original_filename="test.md",
        format=DocumentFormat.MARKDOWN,
        size_bytes=1024,
        language=DetectedLanguage.SPANISH,
        upload_timestamp=datetime(2026, 7, 24, 10, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_extraction_metadata() -> ExtractionMetadata:
    return ExtractionMetadata(
        prompt_version="extraction-v1",
        model_id="gemini/gemini-2.5-flash",
        temperature=0.1,
        element_count=3,
        relationship_count=1,
        verification_rate=0.5,
        extracted_at=datetime(2026, 7, 24, 15, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_ir(sample_metadata: DocumentMetadata) -> IntermediateRepresentation:
    return IntermediateRepresentation(
        document_id="doc-001",
        metadata=sample_metadata,
        chunks=[
            ContentChunkModel(
                chunk_id="chunk-001",
                text="The system processes documents automatically.",
                structural_context={"section": "# Introduction"},
                order=0,
            ),
            ContentChunkModel(
                chunk_id="chunk-002",
                text="Users upload files in PDF or Markdown format.",
                structural_context={"section": "# Features"},
                order=1,
            ),
        ],
    )


@pytest.fixture
def mock_llm_client() -> AsyncMock:
    """Create a mocked LLMClient with AsyncMock for call()."""
    client = AsyncMock()
    return client


def _make_element(
    element_id: str,
    name: str = "Test Element",
    content: str = "Test content for the element",
    verified: bool = True,
    relations: list[Relation] | None = None,
    chunk_id: str = "chunk-001",
) -> KnowledgeElement:
    """Helper to create a KnowledgeElement."""
    return KnowledgeElement(
        id=element_id,
        type="concepto",
        name=name,
        content=content,
        source_ref=SourceRef(
            document_id="doc-001",
            chunk_id=chunk_id,
            evidence=f"Evidence for {name}",
        ),
        relations=relations or [],
        verified=verified,
    )


def _make_km(
    elements: list[KnowledgeElement],
    extraction_metadata: ExtractionMetadata,
) -> KnowledgeModel:
    """Helper to build a KnowledgeModel from elements."""
    return KnowledgeModel(
        document_id="doc-001",
        document_type="generic",
        elements=elements,
        extraction_metadata=extraction_metadata,
    )


def _make_scoring_response(scores: list[dict[str, int | str]]) -> LLMResponse:
    """Helper to create a mocked LLM scoring response."""
    return LLMResponse(
        content=json.dumps(scores),
        model_id="gemini/gemini-2.5-flash",
    )


# --- Test Element Selection with Mocked LLM Scoring ---


class TestElementSelection:
    """Test that ContextBuilder selects elements based on LLM scoring (Req 2.1)."""

    async def test_selects_top_scored_elements(
        self, mock_llm_client, sample_extraction_metadata, sample_ir
    ):
        """Elements with higher scores are selected over lower ones."""
        elements = [
            _make_element("elem-001", name="Actor A"),
            _make_element("elem-002", name="Process B"),
            _make_element("elem-003", name="Rule C"),
        ]
        km = _make_km(elements, sample_extraction_metadata)

        # LLM returns scores: elem-002 highest, elem-001 medium, elem-003 zero
        mock_llm_client.call.return_value = _make_scoring_response([
            {"id": "elem-001", "score": 5},
            {"id": "elem-002", "score": 9},
            {"id": "elem-003", "score": 0},
        ])

        builder = ContextBuilder(mock_llm_client, max_elements=20, budget_ratio=0.6)
        result = await builder.build_context(
            "What is Process B?", km, sample_ir, context_window_tokens=10000
        )

        assert result is not None
        # elem-003 has score 0, should be excluded
        element_ids = [e.element_id for e in result.elements]
        assert "elem-002" in element_ids
        assert "elem-001" in element_ids
        assert "elem-003" not in element_ids

    async def test_elements_ordered_by_score_descending(
        self, mock_llm_client, sample_extraction_metadata, sample_ir
    ):
        """Higher-scored elements appear before lower-scored in the context."""
        elements = [
            _make_element("elem-001", name="Low Score"),
            _make_element("elem-002", name="High Score"),
            _make_element("elem-003", name="Medium Score"),
        ]
        km = _make_km(elements, sample_extraction_metadata)

        mock_llm_client.call.return_value = _make_scoring_response([
            {"id": "elem-001", "score": 2},
            {"id": "elem-002", "score": 10},
            {"id": "elem-003", "score": 6},
        ])

        builder = ContextBuilder(mock_llm_client, max_elements=20, budget_ratio=0.6)
        result = await builder.build_context(
            "Question?", km, sample_ir, context_window_tokens=10000
        )

        assert result is not None
        element_ids = [e.element_id for e in result.elements]
        # Direct elements come before relational, ordered by score
        assert element_ids.index("elem-002") < element_ids.index("elem-003")
        assert element_ids.index("elem-003") < element_ids.index("elem-001")


# --- Test Max 20 Element Cap ---


class TestMaxElementCap:
    """Test that ContextBuilder caps at 20 directly relevant elements (Req 2.1)."""

    async def test_max_20_direct_elements_enforced(
        self, mock_llm_client, sample_extraction_metadata, sample_ir
    ):
        """Even with >20 relevant elements, only 20 are selected."""
        # Create 25 elements all with high scores
        elements = [
            _make_element(f"elem-{i:03d}", name=f"Element {i}")
            for i in range(25)
        ]
        km = _make_km(elements, sample_extraction_metadata)

        # All elements get high scores
        scores = [{"id": f"elem-{i:03d}", "score": 8} for i in range(25)]
        mock_llm_client.call.return_value = _make_scoring_response(scores)

        builder = ContextBuilder(mock_llm_client, max_elements=20, budget_ratio=0.6)
        result = await builder.build_context(
            "Tell me about everything", km, sample_ir, context_window_tokens=100000
        )

        assert result is not None
        # Max 20 elements (all direct, no relational since no relations defined)
        assert len(result.elements) <= 20

    async def test_custom_max_elements_respected(
        self, mock_llm_client, sample_extraction_metadata, sample_ir
    ):
        """Custom max_elements parameter is honored."""
        elements = [
            _make_element(f"elem-{i:03d}", name=f"Element {i}")
            for i in range(10)
        ]
        km = _make_km(elements, sample_extraction_metadata)

        scores = [{"id": f"elem-{i:03d}", "score": 7} for i in range(10)]
        mock_llm_client.call.return_value = _make_scoring_response(scores)

        builder = ContextBuilder(mock_llm_client, max_elements=5, budget_ratio=0.6)
        result = await builder.build_context(
            "Question?", km, sample_ir, context_window_tokens=100000
        )

        assert result is not None
        # Only direct elements since no relations; capped at 5
        assert len(result.elements) <= 5


# --- Test One-Hop Relational Context ---


class TestOneHopRelationalContext:
    """Test that relational context is limited to one hop (Req 2.2)."""

    async def test_includes_one_hop_targets(
        self, mock_llm_client, sample_extraction_metadata, sample_ir
    ):
        """Elements one hop away from direct elements are included."""
        elements = [
            _make_element(
                "elem-001",
                name="Direct Element",
                relations=[
                    Relation(target_id="elem-002", type="depends_on"),
                ],
            ),
            _make_element("elem-002", name="One Hop Target"),
            _make_element("elem-003", name="Unrelated"),
        ]
        km = _make_km(elements, sample_extraction_metadata)

        # Only elem-001 is directly relevant
        mock_llm_client.call.return_value = _make_scoring_response([
            {"id": "elem-001", "score": 9},
            {"id": "elem-002", "score": 0},
            {"id": "elem-003", "score": 0},
        ])

        builder = ContextBuilder(mock_llm_client, max_elements=20, budget_ratio=0.6)
        result = await builder.build_context(
            "What does Direct Element depend on?",
            km, sample_ir, context_window_tokens=10000,
        )

        assert result is not None
        element_ids = [e.element_id for e in result.elements]
        # Direct element is included
        assert "elem-001" in element_ids
        # One-hop target is included via relational context
        assert "elem-002" in element_ids
        # Unrelated element is NOT included
        assert "elem-003" not in element_ids

    async def test_excludes_two_hop_elements(
        self, mock_llm_client, sample_extraction_metadata, sample_ir
    ):
        """Elements two hops away are NOT included."""
        elements = [
            _make_element(
                "elem-001",
                name="Direct",
                relations=[Relation(target_id="elem-002", type="depends_on")],
            ),
            _make_element(
                "elem-002",
                name="One Hop",
                relations=[Relation(target_id="elem-003", type="constrains")],
            ),
            _make_element("elem-003", name="Two Hops Away"),
        ]
        km = _make_km(elements, sample_extraction_metadata)

        # Only elem-001 is directly relevant
        mock_llm_client.call.return_value = _make_scoring_response([
            {"id": "elem-001", "score": 9},
            {"id": "elem-002", "score": 0},
            {"id": "elem-003", "score": 0},
        ])

        builder = ContextBuilder(mock_llm_client, max_elements=20, budget_ratio=0.6)
        result = await builder.build_context(
            "Question?", km, sample_ir, context_window_tokens=10000
        )

        assert result is not None
        element_ids = [e.element_id for e in result.elements]
        assert "elem-001" in element_ids
        assert "elem-002" in element_ids  # one hop
        assert "elem-003" not in element_ids  # two hops — excluded

    async def test_one_hop_does_not_duplicate_direct_elements(
        self, mock_llm_client, sample_extraction_metadata, sample_ir
    ):
        """If a one-hop target is already directly relevant, it isn't duplicated."""
        elements = [
            _make_element(
                "elem-001",
                name="Direct A",
                relations=[Relation(target_id="elem-002", type="depends_on")],
            ),
            _make_element("elem-002", name="Direct B (also one-hop target)"),
        ]
        km = _make_km(elements, sample_extraction_metadata)

        # Both are directly relevant
        mock_llm_client.call.return_value = _make_scoring_response([
            {"id": "elem-001", "score": 9},
            {"id": "elem-002", "score": 7},
        ])

        builder = ContextBuilder(mock_llm_client, max_elements=20, budget_ratio=0.6)
        result = await builder.build_context(
            "Question?", km, sample_ir, context_window_tokens=10000
        )

        assert result is not None
        element_ids = [e.element_id for e in result.elements]
        # No duplicates
        assert element_ids.count("elem-002") == 1


# --- Test 60% Token Budget Enforcement ---


class TestTokenBudgetEnforcement:
    """Test that context respects 60% of context_window_tokens (Req 2.4)."""

    async def test_total_tokens_within_budget(
        self, mock_llm_client, sample_extraction_metadata, sample_ir
    ):
        """Total tokens in result do not exceed 60% of context window."""
        elements = [
            _make_element(f"elem-{i:03d}", name=f"Element {i}", content="x" * 200)
            for i in range(10)
        ]
        km = _make_km(elements, sample_extraction_metadata)

        scores = [{"id": f"elem-{i:03d}", "score": 8} for i in range(10)]
        mock_llm_client.call.return_value = _make_scoring_response(scores)

        context_window = 1000  # small window to force trimming
        builder = ContextBuilder(mock_llm_client, max_elements=20, budget_ratio=0.6)
        result = await builder.build_context(
            "Question?", km, sample_ir, context_window_tokens=context_window
        )

        assert result is not None
        # Total tokens must not exceed 60% of context window
        budget = int(context_window * 0.6)
        assert result.total_tokens <= budget

    async def test_trims_elements_when_budget_exceeded(
        self, mock_llm_client, sample_extraction_metadata, sample_ir
    ):
        """When budget is tight, fewer elements are included."""
        # Create elements with substantial content
        elements = [
            _make_element(
                f"elem-{i:03d}",
                name=f"Element {i}",
                content="A" * 500,  # large content
            )
            for i in range(10)
        ]
        km = _make_km(elements, sample_extraction_metadata)

        scores = [{"id": f"elem-{i:03d}", "score": 8} for i in range(10)]
        mock_llm_client.call.return_value = _make_scoring_response(scores)

        # Very small context window forces heavy trimming
        builder = ContextBuilder(mock_llm_client, max_elements=20, budget_ratio=0.6)
        result = await builder.build_context(
            "Question?", km, sample_ir, context_window_tokens=500
        )

        assert result is not None
        # Should have fewer than 10 elements due to budget
        assert len(result.elements) < 10
        # But at least one element should be present
        assert len(result.elements) >= 1


# --- Test Priority Ordering ---


class TestPriorityOrdering:
    """Test priority: direct > relational > verified over unverified (Req 2.4, 2.5)."""

    async def test_direct_elements_before_relational(
        self, mock_llm_client, sample_extraction_metadata, sample_ir
    ):
        """Direct elements appear before relational elements in the context."""
        elements = [
            _make_element(
                "elem-001",
                name="Direct",
                relations=[Relation(target_id="elem-002", type="depends_on")],
            ),
            _make_element("elem-002", name="Relational Target"),
        ]
        km = _make_km(elements, sample_extraction_metadata)

        # Only elem-001 is directly relevant; elem-002 comes via relation
        mock_llm_client.call.return_value = _make_scoring_response([
            {"id": "elem-001", "score": 8},
            {"id": "elem-002", "score": 0},
        ])

        builder = ContextBuilder(mock_llm_client, max_elements=20, budget_ratio=0.6)
        result = await builder.build_context(
            "Question?", km, sample_ir, context_window_tokens=10000
        )

        assert result is not None
        element_ids = [e.element_id for e in result.elements]
        assert element_ids.index("elem-001") < element_ids.index("elem-002")

    async def test_verified_preferred_over_unverified_at_same_score(
        self, mock_llm_client, sample_extraction_metadata, sample_ir
    ):
        """At the same relevance score, verified elements rank higher."""
        elements = [
            _make_element("elem-001", name="Unverified", verified=False),
            _make_element("elem-002", name="Verified", verified=True),
        ]
        km = _make_km(elements, sample_extraction_metadata)

        # Same score for both
        mock_llm_client.call.return_value = _make_scoring_response([
            {"id": "elem-001", "score": 7},
            {"id": "elem-002", "score": 7},
        ])

        builder = ContextBuilder(mock_llm_client, max_elements=20, budget_ratio=0.6)
        result = await builder.build_context(
            "Question?", km, sample_ir, context_window_tokens=10000
        )

        assert result is not None
        element_ids = [e.element_id for e in result.elements]
        # Verified element should be listed before unverified at same score
        assert element_ids.index("elem-002") < element_ids.index("elem-001")


# --- Test Fallback Behavior ---


class TestFallbackBehavior:
    """Test fallback when scoring LLM fails (Req 2.1 design decision)."""

    async def test_fallback_includes_elements_on_llm_failure(
        self, mock_llm_client, sample_extraction_metadata, sample_ir
    ):
        """When LLM scoring fails, all elements are included up to budget."""
        elements = [
            _make_element("elem-001", name="Element A"),
            _make_element("elem-002", name="Element B"),
            _make_element("elem-003", name="Element C"),
        ]
        km = _make_km(elements, sample_extraction_metadata)

        # LLM call raises an exception
        mock_llm_client.call.side_effect = Exception("LLM service unavailable")

        builder = ContextBuilder(mock_llm_client, max_elements=20, budget_ratio=0.6)
        result = await builder.build_context(
            "Question?", km, sample_ir, context_window_tokens=10000
        )

        assert result is not None
        # All elements should be included (fallback assigns score=1 to all)
        element_ids = [e.element_id for e in result.elements]
        assert "elem-001" in element_ids
        assert "elem-002" in element_ids
        assert "elem-003" in element_ids

    async def test_fallback_still_respects_token_budget(
        self, mock_llm_client, sample_extraction_metadata, sample_ir
    ):
        """Even in fallback mode, token budget is still enforced."""
        elements = [
            _make_element(
                f"elem-{i:03d}", name=f"Element {i}", content="B" * 500
            )
            for i in range(10)
        ]
        km = _make_km(elements, sample_extraction_metadata)

        mock_llm_client.call.side_effect = Exception("LLM error")

        # Very small budget
        builder = ContextBuilder(mock_llm_client, max_elements=20, budget_ratio=0.6)
        result = await builder.build_context(
            "Question?", km, sample_ir, context_window_tokens=500
        )

        assert result is not None
        budget = int(500 * 0.6)
        assert result.total_tokens <= budget


# --- Test Returns None When No Elements Are Relevant ---


class TestReturnsNoneForNoRelevantElements:
    """Test that None is returned when no elements are relevant (Req 2.7)."""

    async def test_none_when_all_scores_zero(
        self, mock_llm_client, sample_extraction_metadata, sample_ir
    ):
        """If all elements score 0, build_context returns None."""
        elements = [
            _make_element("elem-001", name="Element A"),
            _make_element("elem-002", name="Element B"),
        ]
        km = _make_km(elements, sample_extraction_metadata)

        mock_llm_client.call.return_value = _make_scoring_response([
            {"id": "elem-001", "score": 0},
            {"id": "elem-002", "score": 0},
        ])

        builder = ContextBuilder(mock_llm_client, max_elements=20, budget_ratio=0.6)
        result = await builder.build_context(
            "Completely unrelated question?",
            km, sample_ir, context_window_tokens=10000,
        )

        assert result is None

    async def test_none_when_knowledge_model_is_empty(
        self, mock_llm_client, sample_extraction_metadata, sample_ir
    ):
        """If KM has zero elements, build_context returns None."""
        km = _make_km([], sample_extraction_metadata)

        builder = ContextBuilder(mock_llm_client, max_elements=20, budget_ratio=0.6)
        result = await builder.build_context(
            "Any question?", km, sample_ir, context_window_tokens=10000
        )

        assert result is None
        # LLM should not be called when there are no elements
        mock_llm_client.call.assert_not_called()


# --- Test Unverified Element Annotation ---


class TestUnverifiedElementAnnotation:
    """Test that unverified elements are annotated with [UNVERIFIED] (Req 2.5)."""

    async def test_unverified_element_gets_annotation_in_content(
        self, mock_llm_client, sample_extraction_metadata, sample_ir
    ):
        """Unverified elements have [UNVERIFIED] prefix in their content."""
        elements = [
            _make_element("elem-001", name="Verified Elem", verified=True),
            _make_element("elem-002", name="Unverified Elem", verified=False),
        ]
        km = _make_km(elements, sample_extraction_metadata)

        mock_llm_client.call.return_value = _make_scoring_response([
            {"id": "elem-001", "score": 8},
            {"id": "elem-002", "score": 7},
        ])

        builder = ContextBuilder(mock_llm_client, max_elements=20, budget_ratio=0.6)
        result = await builder.build_context(
            "Question?", km, sample_ir, context_window_tokens=10000
        )

        assert result is not None
        # Find the unverified element
        unverified = next(e for e in result.elements if e.element_id == "elem-002")
        assert unverified.content.startswith("[UNVERIFIED]")
        assert unverified.verified is False

        # Verified element should NOT have the annotation
        verified = next(e for e in result.elements if e.element_id == "elem-001")
        assert not verified.content.startswith("[UNVERIFIED]")
        assert verified.verified is True

    async def test_has_unverified_elements_flag_set(
        self, mock_llm_client, sample_extraction_metadata, sample_ir
    ):
        """QueryContext.has_unverified_elements is True when unverified present."""
        elements = [
            _make_element("elem-001", name="Verified", verified=True),
            _make_element("elem-002", name="Unverified", verified=False),
        ]
        km = _make_km(elements, sample_extraction_metadata)

        mock_llm_client.call.return_value = _make_scoring_response([
            {"id": "elem-001", "score": 8},
            {"id": "elem-002", "score": 7},
        ])

        builder = ContextBuilder(mock_llm_client, max_elements=20, budget_ratio=0.6)
        result = await builder.build_context(
            "Question?", km, sample_ir, context_window_tokens=10000
        )

        assert result is not None
        assert result.has_unverified_elements is True

    async def test_has_unverified_elements_flag_false_when_all_verified(
        self, mock_llm_client, sample_extraction_metadata, sample_ir
    ):
        """QueryContext.has_unverified_elements is False when all are verified."""
        elements = [
            _make_element("elem-001", name="Verified A", verified=True),
            _make_element("elem-002", name="Verified B", verified=True),
        ]
        km = _make_km(elements, sample_extraction_metadata)

        mock_llm_client.call.return_value = _make_scoring_response([
            {"id": "elem-001", "score": 8},
            {"id": "elem-002", "score": 7},
        ])

        builder = ContextBuilder(mock_llm_client, max_elements=20, budget_ratio=0.6)
        result = await builder.build_context(
            "Question?", km, sample_ir, context_window_tokens=10000
        )

        assert result is not None
        assert result.has_unverified_elements is False
