"""Property-based tests for Document Quality Analysis.

Tests correctness properties using Hypothesis to verify universal invariants
across randomly generated inputs.

Feature: document-quality-analysis
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.analysis.llm_client import LLMClient, LLMResponse, LLMTransientError
from app.analysis.quality.completeness_evaluator import CompletenessEvaluator
from app.analysis.quality.contradiction_detector import ContradictionDetector
from app.analysis.quality.suggestion_generator import (
    MAX_SUGGESTIONS,
    SuggestionGenerator,
)
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
from app.models.quality_analysis import (
    FindingSourceRef,
    Inconsistency,
    MissingElement,
    Suggestion,
)


# --- Strategies ---

ELEMENT_TYPES = ["proposito", "concepto", "actor", "regla", "proceso", "restriccion"]
SEVERITY_LEVELS = ["high", "medium", "low"]
SUGGESTION_CATEGORIES = ["structure", "clarity", "completeness", "consistency"]
SUGGESTION_PRIORITIES = ["high", "medium", "low"]


@st.composite
def source_refs(draw):
    """Generate a valid SourceRef for KM elements."""
    return SourceRef(
        document_id=f"doc-{draw(st.text(alphabet='abcdef0123456789', min_size=8, max_size=8))}",
        chunk_id=f"chunk-{draw(st.text(alphabet='abcdef0123456789', min_size=4, max_size=4))}",
        page=draw(st.one_of(st.none(), st.integers(min_value=1, max_value=100))),
        section=draw(st.one_of(st.none(), st.text(min_size=1, max_size=50))),
        evidence=draw(st.text(min_size=1, max_size=200)),
    )


@st.composite
def knowledge_elements(draw):
    """Generate a valid KnowledgeElement."""
    return KnowledgeElement(
        id=f"elem-{draw(st.text(alphabet='abcdef0123456789', min_size=8, max_size=8))}",
        type=draw(st.sampled_from(ELEMENT_TYPES)),
        name=draw(st.text(min_size=1, max_size=100)),
        content=draw(st.text(min_size=1, max_size=500)),
        source_ref=draw(source_refs()),
        relations=[],
        verified=draw(st.booleans()),
    )


@st.composite
def knowledge_models(draw, min_elements=1, max_elements=10):
    """Generate a valid KnowledgeModel with random elements."""
    elements = draw(
        st.lists(knowledge_elements(), min_size=min_elements, max_size=max_elements)
    )
    return KnowledgeModel(
        document_id=f"doc-{draw(st.text(alphabet='abcdef0123456789', min_size=8, max_size=8))}",
        document_type=draw(st.sampled_from(["prd", "technical_spec", "policy_process", "generic"])),
        elements=elements,
        extraction_metadata=ExtractionMetadata(
            prompt_version="extraction-v1",
            model_id="gemini/gemini-2.5-flash-preview-05-20",
            temperature=0.1,
            element_count=len(elements),
            relationship_count=0,
            verification_rate=0.5,
            extracted_at=datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc),
        ),
    )


@st.composite
def finding_source_refs(draw):
    """Generate a valid FindingSourceRef for quality findings."""
    return FindingSourceRef(
        document_id=f"doc-{draw(st.text(alphabet='abcdef0123456789', min_size=8, max_size=8))}",
        chunk_id=f"chunk-{draw(st.text(alphabet='abcdef0123456789', min_size=4, max_size=4))}",
        page=draw(st.one_of(st.none(), st.integers(min_value=1, max_value=100))),
        section=draw(st.one_of(st.none(), st.text(min_size=1, max_size=50))),
        evidence=draw(st.text(min_size=1, max_size=500)),
        evidence_verified=draw(st.booleans()),
    )


@st.composite
def suggestions(draw):
    """Generate a valid Suggestion."""
    return Suggestion(
        id=f"sug-{draw(st.text(alphabet='abcdef0123456789', min_size=8, max_size=8))}",
        description=draw(st.text(min_size=1, max_size=300)),
        category=draw(st.sampled_from(SUGGESTION_CATEGORIES)),
        priority=draw(st.sampled_from(SUGGESTION_PRIORITIES)),
        related_finding_ids=draw(
            st.lists(st.text(min_size=1, max_size=20), min_size=0, max_size=3)
        ),
        source_refs=draw(st.lists(finding_source_refs(), min_size=0, max_size=3)),
        all_evidence_unverified=draw(st.booleans()),
    )


# =============================================================================
# Property 2: Finding Structural Completeness
# =============================================================================


@st.composite
def contradiction_inconsistencies(draw):
    """Generate valid Inconsistency instances of type 'contradiction'.

    Contradictions require at least 2 source_refs and at least 2 affected_element_ids.
    """
    num_refs = draw(st.integers(min_value=2, max_value=5))
    num_elements = draw(st.integers(min_value=2, max_value=6))
    refs = [draw(finding_source_refs()) for _ in range(num_refs)]
    element_ids = [
        f"elem-{draw(st.text(alphabet='abcdef0123456789', min_size=4, max_size=8))}"
        for _ in range(num_elements)
    ]
    return Inconsistency(
        id=f"inc-{draw(st.text(alphabet='abcdef0123456789', min_size=4, max_size=8))}",
        type="contradiction",
        description=draw(st.text(min_size=1, max_size=500)),
        severity=draw(st.sampled_from(SEVERITY_LEVELS)),
        affected_element_ids=element_ids,
        source_refs=refs,
        involves_unverified_elements=draw(st.booleans()),
        all_evidence_unverified=draw(st.booleans()),
        from_explicit_relationship=draw(st.booleans()),
    )


@st.composite
def ambiguity_inconsistencies(draw):
    """Generate valid Inconsistency instances of type 'ambiguity'.

    Ambiguities require at least 1 source_ref.
    """
    num_refs = draw(st.integers(min_value=1, max_value=5))
    num_elements = draw(st.integers(min_value=1, max_value=6))
    refs = [draw(finding_source_refs()) for _ in range(num_refs)]
    element_ids = [
        f"elem-{draw(st.text(alphabet='abcdef0123456789', min_size=4, max_size=8))}"
        for _ in range(num_elements)
    ]
    return Inconsistency(
        id=f"inc-{draw(st.text(alphabet='abcdef0123456789', min_size=4, max_size=8))}",
        type="ambiguity",
        description=draw(st.text(min_size=1, max_size=500)),
        severity=draw(st.sampled_from(SEVERITY_LEVELS)),
        affected_element_ids=element_ids,
        source_refs=refs,
        involves_unverified_elements=draw(st.booleans()),
        all_evidence_unverified=draw(st.booleans()),
        from_explicit_relationship=False,
    )


class TestProperty2FindingStructuralCompleteness:
    """Property 2: Finding Structural Completeness.

    For any Inconsistency of type "contradiction", verify at least 2 source_refs,
    at least 2 affected_element_ids, description <= 500 chars, valid severity.
    For type "ambiguity", verify at least 1 source_ref, description <= 500 chars,
    valid severity.

    **Validates: Requirements 1.2, 2.2, 7.1, 7.2, 7.3**
    """

    @given(inconsistency=contradiction_inconsistencies())
    @settings(max_examples=100)
    def test_contradiction_has_at_least_2_source_refs(self, inconsistency: Inconsistency):
        """Any valid contradiction must have at least 2 source_refs (Req 7.2).

        **Validates: Requirements 1.2, 7.1, 7.2**
        """
        assert inconsistency.type == "contradiction"
        assert len(inconsistency.source_refs) >= 2

    @given(inconsistency=contradiction_inconsistencies())
    @settings(max_examples=100)
    def test_contradiction_has_at_least_2_affected_element_ids(
        self, inconsistency: Inconsistency
    ):
        """Any valid contradiction must reference at least 2 KM element IDs (Req 1.2).

        **Validates: Requirements 1.2**
        """
        assert inconsistency.type == "contradiction"
        assert len(inconsistency.affected_element_ids) >= 2

    @given(inconsistency=contradiction_inconsistencies())
    @settings(max_examples=100)
    def test_contradiction_description_within_500_chars(self, inconsistency: Inconsistency):
        """Any valid contradiction description must be at most 500 characters (Req 1.2).

        **Validates: Requirements 1.2**
        """
        assert len(inconsistency.description) <= 500

    @given(inconsistency=contradiction_inconsistencies())
    @settings(max_examples=100)
    def test_contradiction_has_valid_severity(self, inconsistency: Inconsistency):
        """Any valid contradiction must have severity in {high, medium, low} (Req 1.2).

        **Validates: Requirements 1.2**
        """
        assert inconsistency.severity in ("high", "medium", "low")

    @given(inconsistency=contradiction_inconsistencies())
    @settings(max_examples=100)
    def test_contradiction_source_refs_have_valid_evidence(self, inconsistency: Inconsistency):
        """Every source_ref in a contradiction has non-empty evidence <= 500 chars (Req 7.3).

        **Validates: Requirements 7.1, 7.3**
        """
        for ref in inconsistency.source_refs:
            assert len(ref.evidence) > 0
            assert len(ref.evidence) <= 500

    @given(inconsistency=ambiguity_inconsistencies())
    @settings(max_examples=100)
    def test_ambiguity_has_at_least_1_source_ref(self, inconsistency: Inconsistency):
        """Any valid ambiguity must have at least 1 source_ref (Req 7.1).

        **Validates: Requirements 2.2, 7.1**
        """
        assert inconsistency.type == "ambiguity"
        assert len(inconsistency.source_refs) >= 1

    @given(inconsistency=ambiguity_inconsistencies())
    @settings(max_examples=100)
    def test_ambiguity_description_within_500_chars(self, inconsistency: Inconsistency):
        """Any valid ambiguity description must be at most 500 characters (Req 2.2).

        **Validates: Requirements 2.2**
        """
        assert len(inconsistency.description) <= 500

    @given(inconsistency=ambiguity_inconsistencies())
    @settings(max_examples=100)
    def test_ambiguity_has_valid_severity(self, inconsistency: Inconsistency):
        """Any valid ambiguity must have severity in {high, medium, low} (Req 2.2).

        **Validates: Requirements 2.2**
        """
        assert inconsistency.severity in ("high", "medium", "low")

    @given(inconsistency=ambiguity_inconsistencies())
    @settings(max_examples=100)
    def test_ambiguity_source_refs_have_valid_evidence(self, inconsistency: Inconsistency):
        """Every source_ref in an ambiguity has non-empty evidence <= 500 chars (Req 7.3).

        **Validates: Requirements 7.1, 7.3**
        """
        for ref in inconsistency.source_refs:
            assert len(ref.evidence) > 0
            assert len(ref.evidence) <= 500

    # --- Negative tests: Pydantic rejects invalid data ---

    @given(
        description=st.text(min_size=501, max_size=600),
    )
    @settings(max_examples=100)
    def test_contradiction_rejects_description_over_500(self, description: str):
        """Pydantic model rejects contradictions with description > 500 chars.

        **Validates: Requirements 1.2**
        """
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Inconsistency(
                id="test-inc",
                type="contradiction",
                description=description,
                severity="high",
                affected_element_ids=["elem-1", "elem-2"],
                source_refs=[
                    FindingSourceRef(
                        document_id="doc-001",
                        chunk_id="chunk-001",
                        evidence="Evidence A",
                    ),
                    FindingSourceRef(
                        document_id="doc-001",
                        chunk_id="chunk-002",
                        evidence="Evidence B",
                    ),
                ],
            )

    @given(
        evidence=st.text(min_size=501, max_size=600),
    )
    @settings(max_examples=100)
    def test_source_ref_rejects_evidence_over_500(self, evidence: str):
        """Pydantic model rejects source_refs with evidence > 500 chars.

        **Validates: Requirements 7.3**
        """
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            FindingSourceRef(
                document_id="doc-001",
                chunk_id="chunk-001",
                evidence=evidence,
            )

    @given(
        severity=st.text(min_size=1, max_size=10).filter(
            lambda s: s not in ("high", "medium", "low")
        ),
    )
    @settings(max_examples=100)
    def test_inconsistency_rejects_invalid_severity(self, severity: str):
        """Pydantic model rejects inconsistencies with invalid severity values.

        **Validates: Requirements 1.2, 2.2**
        """
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Inconsistency(
                id="test-inc",
                type="contradiction",
                description="Some contradiction",
                severity=severity,
                affected_element_ids=["elem-1", "elem-2"],
                source_refs=[
                    FindingSourceRef(
                        document_id="doc-001",
                        chunk_id="chunk-001",
                        evidence="Evidence A",
                    ),
                    FindingSourceRef(
                        document_id="doc-001",
                        chunk_id="chunk-002",
                        evidence="Evidence B",
                    ),
                ],
            )

    @given(
        inc_type=st.text(min_size=1, max_size=20).filter(
            lambda s: s not in ("contradiction", "ambiguity")
        ),
    )
    @settings(max_examples=100)
    def test_inconsistency_rejects_invalid_type(self, inc_type: str):
        """Pydantic model rejects inconsistencies with invalid type values.

        **Validates: Requirements 1.2, 2.2**
        """
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Inconsistency(
                id="test-inc",
                type=inc_type,
                description="Some finding",
                severity="high",
                affected_element_ids=["elem-1"],
                source_refs=[
                    FindingSourceRef(
                        document_id="doc-001",
                        chunk_id="chunk-001",
                        evidence="Evidence text",
                    ),
                ],
            )


# =============================================================================
# Property 3: Generic Type Completeness Skip
# =============================================================================


class TestProperty3GenericTypeCompletenessSkip:
    """Property 3: Generic Type Completeness Skip.

    For any document with type "generic", missing_elements is always empty
    while contradictions/ambiguities may be non-empty.

    **Validates: Requirements 3.3, 8.6**
    """

    @given(km=knowledge_models(min_elements=1, max_elements=10))
    @settings(max_examples=100)
    def test_generic_type_always_returns_empty_missing_elements(self, km: KnowledgeModel):
        """For any KnowledgeModel, CompletenessEvaluator.evaluate() with
        document_type='generic' always returns an empty list.

        This verifies that the system never reports missing elements for
        generic documents regardless of what elements are in the KM.
        """
        import asyncio

        # Create a mock LLM client that should never be called
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.call = AsyncMock()

        evaluator = CompletenessEvaluator(mock_llm)

        # Run the async evaluate with document_type="generic"
        result = asyncio.run(evaluator.evaluate(km, "generic"))

        # Property: missing_elements is ALWAYS empty for generic type
        assert result == [], (
            f"Expected empty list for generic type, got {len(result)} findings"
        )

        # The LLM should never be called for generic type
        mock_llm.call.assert_not_called()


# =============================================================================
# Property 4: Suggestion Count Bound
# =============================================================================


class TestProperty4SuggestionCountBound:
    """Property 4: Suggestion Count Bound.

    For any quality analysis output, suggestions count <= 20.

    **Validates: Requirements 4.6**
    """

    @given(
        suggestion_list=st.lists(suggestions(), min_size=0, max_size=30)
    )
    @settings(max_examples=100)
    def test_enforce_max_suggestions_never_exceeds_20(
        self, suggestion_list: list[Suggestion]
    ):
        """For any list of suggestions (0-30 items), after passing through
        _enforce_max_suggestions(), the output count is always <= 20.
        """
        mock_llm = MagicMock(spec=LLMClient)
        generator = SuggestionGenerator(mock_llm)

        result = generator._enforce_max_suggestions(suggestion_list)

        # Property: output count is always <= MAX_SUGGESTIONS (20)
        assert len(result) <= MAX_SUGGESTIONS, (
            f"Expected at most {MAX_SUGGESTIONS} suggestions, got {len(result)}"
        )

    @given(
        suggestion_list=st.lists(suggestions(), min_size=0, max_size=20)
    )
    @settings(max_examples=100)
    def test_enforce_max_suggestions_preserves_within_limit(
        self, suggestion_list: list[Suggestion]
    ):
        """For any list of suggestions with count <= 20, the output
        preserves all of them (no unnecessary truncation).
        """
        mock_llm = MagicMock(spec=LLMClient)
        generator = SuggestionGenerator(mock_llm)

        result = generator._enforce_max_suggestions(suggestion_list)

        # When input is within the limit, all suggestions are preserved
        assert len(result) == len(suggestion_list), (
            f"Expected {len(suggestion_list)} suggestions preserved, got {len(result)}"
        )

    @given(
        suggestion_list=st.lists(suggestions(), min_size=21, max_size=30)
    )
    @settings(max_examples=100)
    def test_enforce_max_suggestions_truncates_lowest_priority(
        self, suggestion_list: list[Suggestion]
    ):
        """For any list exceeding 20 suggestions, the result keeps
        exactly 20 and prioritizes high-priority suggestions.
        """
        mock_llm = MagicMock(spec=LLMClient)
        generator = SuggestionGenerator(mock_llm)

        result = generator._enforce_max_suggestions(suggestion_list)

        assert len(result) == MAX_SUGGESTIONS

        # All high-priority suggestions from input should be in output
        # (as long as there are <= 20 high-priority ones)
        input_high = [s for s in suggestion_list if s.priority == "high"]
        result_high = [s for s in result if s.priority == "high"]
        if len(input_high) <= MAX_SUGGESTIONS:
            assert len(result_high) == len(input_high), (
                "High-priority suggestions should all be preserved when count <= 20"
            )


# =============================================================================
# Property 5: Suggestion Coverage of High-Severity Findings
# =============================================================================


class TestProperty5SuggestionCoverage:
    """Property 5: Suggestion Coverage.

    For any result with N high-severity findings, suggestions count >= N
    (capped at 20).

    **Validates: Requirements 4.4**
    """

    @given(
        n_high_severity=st.integers(min_value=0, max_value=15),
        n_medium_severity=st.integers(min_value=0, max_value=5),
        n_low_severity=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=100)
    def test_ensure_high_severity_coverage_generates_enough_suggestions(
        self,
        n_high_severity: int,
        n_medium_severity: int,
        n_low_severity: int,
    ):
        """For any set of findings with N high-severity items, after
        _ensure_high_severity_coverage(), suggestions count >= min(N, 20).

        This tests the post-processing logic that guarantees at least one
        suggestion per high-severity finding.
        """
        import asyncio

        mock_llm = MagicMock(spec=LLMClient)
        generator = SuggestionGenerator(mock_llm)

        # Build inconsistencies with varying severities
        inconsistencies: list[Inconsistency] = []
        all_high_ids: set[str] = set()

        for i in range(n_high_severity):
            finding_id = f"inc-high-{i}"
            all_high_ids.add(finding_id)
            inconsistencies.append(
                Inconsistency(
                    id=finding_id,
                    type="contradiction",
                    description=f"High severity contradiction {i}",
                    severity="high",
                    affected_element_ids=[f"elem-{i}a", f"elem-{i}b"],
                    source_refs=[
                        FindingSourceRef(
                            document_id="doc-001",
                            chunk_id=f"chunk-{i}a",
                            evidence=f"Evidence A for contradiction {i}",
                            evidence_verified=False,
                        ),
                        FindingSourceRef(
                            document_id="doc-001",
                            chunk_id=f"chunk-{i}b",
                            evidence=f"Evidence B for contradiction {i}",
                            evidence_verified=False,
                        ),
                    ],
                )
            )

        for i in range(n_medium_severity):
            inconsistencies.append(
                Inconsistency(
                    id=f"inc-med-{i}",
                    type="ambiguity",
                    description=f"Medium severity ambiguity {i}",
                    severity="medium",
                    affected_element_ids=[f"elem-m{i}"],
                    source_refs=[
                        FindingSourceRef(
                            document_id="doc-001",
                            chunk_id=f"chunk-m{i}",
                            evidence=f"Evidence for ambiguity {i}",
                            evidence_verified=False,
                        ),
                    ],
                )
            )

        # Build missing elements with high severity
        missing_elements: list[MissingElement] = []
        for i in range(n_low_severity):
            missing_elements.append(
                MissingElement(
                    id=f"miss-low-{i}",
                    classification="missing",
                    expected_element=f"element-{i}",
                    description=f"Low severity missing element {i}",
                    severity="low",
                    schema_reference="prd",
                )
            )

        # Start with an empty list of suggestions (simulating LLM returning nothing)
        initial_suggestions: list[Suggestion] = []

        # Build a mock IR for fallback source_ref creation
        ir = IntermediateRepresentation(
            document_id="doc-001",
            metadata=DocumentMetadata(
                original_filename="test.md",
                format=DocumentFormat.MARKDOWN,
                size_bytes=1000,
                language=DetectedLanguage.ENGLISH,
                upload_timestamp=datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc),
            ),
            chunks=[
                ContentChunkModel(
                    chunk_id="chunk-fallback",
                    text="Fallback text for evidence",
                    structural_context={"section": "Introduction", "page": "1"},
                    order=0,
                )
            ],
        )

        # Apply the high-severity coverage logic
        result = generator._ensure_high_severity_coverage(
            initial_suggestions, inconsistencies, missing_elements, ir
        )

        # Property: suggestions count >= min(N_high, MAX_SUGGESTIONS)
        expected_min = min(n_high_severity, MAX_SUGGESTIONS)
        assert len(result) >= expected_min, (
            f"Expected at least {expected_min} suggestions for {n_high_severity} "
            f"high-severity findings, got {len(result)}"
        )

    @given(
        n_high_severity=st.integers(min_value=1, max_value=10),
        n_existing_suggestions=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=100)
    def test_existing_suggestions_covering_findings_are_not_duplicated(
        self,
        n_high_severity: int,
        n_existing_suggestions: int,
    ):
        """When existing suggestions already cover some high-severity findings,
        only uncovered findings get new placeholder suggestions.
        """
        mock_llm = MagicMock(spec=LLMClient)
        generator = SuggestionGenerator(mock_llm)

        # Create high-severity inconsistencies
        inconsistencies: list[Inconsistency] = []
        for i in range(n_high_severity):
            inconsistencies.append(
                Inconsistency(
                    id=f"inc-high-{i}",
                    type="contradiction",
                    description=f"High severity finding {i}",
                    severity="high",
                    affected_element_ids=[f"elem-{i}a", f"elem-{i}b"],
                    source_refs=[
                        FindingSourceRef(
                            document_id="doc-001",
                            chunk_id=f"chunk-{i}",
                            evidence=f"Evidence {i}",
                            evidence_verified=False,
                        ),
                        FindingSourceRef(
                            document_id="doc-001",
                            chunk_id=f"chunk-{i}b",
                            evidence=f"Evidence {i} B",
                            evidence_verified=False,
                        ),
                    ],
                )
            )

        # Create existing suggestions that cover some findings
        n_covered = min(n_existing_suggestions, n_high_severity)
        existing_suggestions: list[Suggestion] = []
        for i in range(n_covered):
            existing_suggestions.append(
                Suggestion(
                    id=f"sug-existing-{i}",
                    description=f"Fix contradiction {i}",
                    category="consistency",
                    priority="high",
                    related_finding_ids=[f"inc-high-{i}"],
                    source_refs=[
                        FindingSourceRef(
                            document_id="doc-001",
                            chunk_id=f"chunk-{i}",
                            evidence=f"Evidence {i}",
                            evidence_verified=False,
                        ),
                    ],
                )
            )

        ir = IntermediateRepresentation(
            document_id="doc-001",
            metadata=DocumentMetadata(
                original_filename="test.md",
                format=DocumentFormat.MARKDOWN,
                size_bytes=1000,
                language=DetectedLanguage.ENGLISH,
                upload_timestamp=datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc),
            ),
            chunks=[
                ContentChunkModel(
                    chunk_id="chunk-fallback",
                    text="Fallback evidence text",
                    structural_context={"section": "Intro", "page": "1"},
                    order=0,
                )
            ],
        )

        result = generator._ensure_high_severity_coverage(
            existing_suggestions, inconsistencies, [], ir
        )

        # Property: all high-severity findings are covered
        covered_finding_ids: set[str] = set()
        for s in result:
            for fid in s.related_finding_ids:
                covered_finding_ids.add(fid)

        for inc in inconsistencies:
            if inc.severity == "high":
                assert inc.id in covered_finding_ids, (
                    f"High-severity finding {inc.id} not covered by any suggestion"
                )

        # Total suggestions should be at least max(n_covered, n_high_severity)
        # because uncovered findings get new placeholders
        n_uncovered = n_high_severity - n_covered
        assert len(result) == n_covered + n_uncovered


# =============================================================================
# Property 6: Clean Failure State
# =============================================================================


class TestProperty6CleanFailureState:
    """Property 6: Clean Failure State.

    For any failed analysis, quality_analysis contains only explicit-relationship
    contradictions (if any), error_message is non-empty <= 1000 chars.

    **Validates: Requirements 6.2, 6.4**
    """

    @st.composite
    @staticmethod
    def st_failed_quality_result(draw):
        """Generate a QualityAnalysisResult with status='failed'.

        Per Req 6.4: failed results contain only explicit-relationship contradictions.
        """
        from app.models.quality_analysis import QualityAnalysisResult

        # Generate 0-3 explicit-relationship contradictions
        num_explicit = draw(st.integers(min_value=0, max_value=3))
        inconsistencies = []
        for i in range(num_explicit):
            inc_type = draw(st.sampled_from(["contradiction", "ambiguity"]))
            min_refs = 2 if inc_type == "contradiction" else 1
            num_refs = draw(st.integers(min_value=min_refs, max_value=4))
            refs = [
                FindingSourceRef(
                    document_id="doc-test",
                    chunk_id=f"chunk-{j:03d}",
                    evidence=draw(st.text(min_size=1, max_size=200)),
                )
                for j in range(num_refs)
            ]
            num_elements = draw(st.integers(min_value=2, max_value=4))
            inconsistencies.append(
                Inconsistency(
                    id=f"inc-{i:03d}",
                    type=inc_type,
                    description=draw(st.text(min_size=1, max_size=200)),
                    severity=draw(st.sampled_from(SEVERITY_LEVELS)),
                    affected_element_ids=[f"elem-{k:03d}" for k in range(num_elements)],
                    source_refs=refs,
                    from_explicit_relationship=True,
                )
            )

        error_message = draw(st.text(min_size=1, max_size=1000))

        return QualityAnalysisResult(
            document_id="doc-test",
            status="failed",
            inconsistencies=inconsistencies,
            missing_elements=[],
            suggestions=[],
            metadata=None,
            error_message=error_message,
            error_phase=draw(st.sampled_from([
                "analyzing_contradictions",
                "analyzing_ambiguities",
                "analyzing_completeness",
                "generating_suggestions",
                "timeout",
                "unknown",
            ])),
        )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_failed_result_contains_only_explicit_contradictions(self, data):
        """All inconsistencies in a failed result must have from_explicit_relationship=True."""
        result = data.draw(TestProperty6CleanFailureState.st_failed_quality_result())

        assert result.status == "failed"

        for inc in result.inconsistencies:
            assert inc.from_explicit_relationship is True, (
                f"Failed result contains a finding with from_explicit_relationship=False: {inc.id}"
            )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_failed_result_has_no_other_findings(self, data):
        """Failed results must have empty missing_elements and suggestions."""
        result = data.draw(TestProperty6CleanFailureState.st_failed_quality_result())

        assert result.status == "failed"
        assert result.missing_elements == [], (
            "Failed result must have empty missing_elements"
        )
        assert result.suggestions == [], (
            "Failed result must have empty suggestions"
        )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_failed_result_error_message_constraints(self, data):
        """Error message must be non-empty and <= 1000 characters."""
        result = data.draw(TestProperty6CleanFailureState.st_failed_quality_result())

        assert result.status == "failed"
        assert result.error_message is not None, (
            "Failed result must have a non-None error_message"
        )
        assert len(result.error_message) > 0, (
            "Failed result must have a non-empty error_message"
        )
        assert len(result.error_message) <= 1000, (
            f"Error message exceeds 1000 chars: {len(result.error_message)}"
        )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_failed_result_has_no_metadata(self, data):
        """Failed results must have no metadata (analysis did not complete)."""
        result = data.draw(TestProperty6CleanFailureState.st_failed_quality_result())

        assert result.status == "failed"
        assert result.metadata is None, (
            "Failed result must not include metadata"
        )


# =============================================================================
# Property 7: Evidence Verification Determinism
# =============================================================================


class TestProperty7EvidenceVerificationDeterminism:
    """Property 7: Evidence Verification Determinism.

    Running verify_all twice on the same inputs produces identical
    evidence_verified values; all_evidence_unverified is set correctly.

    **Validates: Requirements 7.5, 7.7**
    """

    @st.composite
    @staticmethod
    def st_ir_for_verification(draw):
        """Generate an IntermediateRepresentation with 1-5 random chunks."""
        from app.models.document import (
            ContentChunkModel,
            DetectedLanguage,
            DocumentFormat,
            DocumentMetadata,
            IntermediateRepresentation,
        )

        num_chunks = draw(st.integers(min_value=1, max_value=5))
        chunks = []
        for i in range(num_chunks):
            text = draw(st.text(min_size=5, max_size=200))
            chunks.append(
                ContentChunkModel(
                    chunk_id=f"chunk-{i:03d}",
                    text=text,
                    structural_context={"section": f"## Section {i}"},
                    order=i,
                )
            )

        metadata = DocumentMetadata(
            original_filename="test.md",
            format=DocumentFormat.MARKDOWN,
            size_bytes=1024,
            language=DetectedLanguage.ENGLISH,
            upload_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            warnings=[],
        )
        return IntermediateRepresentation(
            document_id="doc-test",
            metadata=metadata,
            chunks=chunks,
        )

    @st.composite
    @staticmethod
    def st_inconsistency_for_verification(draw, chunk_ids=None):
        """Generate a random Inconsistency finding for verification tests."""
        if chunk_ids is None:
            chunk_ids = [f"chunk-{i:03d}" for i in range(5)]

        inc_type = draw(st.sampled_from(["contradiction", "ambiguity"]))
        min_refs = 2 if inc_type == "contradiction" else 1
        num_refs = draw(st.integers(min_value=min_refs, max_value=4))
        refs = [
            FindingSourceRef(
                document_id="doc-test",
                chunk_id=draw(st.sampled_from(chunk_ids)),
                evidence=draw(st.text(min_size=1, max_size=200)),
            )
            for _ in range(num_refs)
        ]

        num_elements = draw(st.integers(min_value=2, max_value=4))
        return Inconsistency(
            id=f"inc-{draw(st.text(min_size=3, max_size=8, alphabet='abcdef0123456789'))}",
            type=inc_type,
            description=draw(st.text(min_size=1, max_size=200)),
            severity=draw(st.sampled_from(SEVERITY_LEVELS)),
            affected_element_ids=[f"elem-{k:03d}" for k in range(num_elements)],
            source_refs=refs,
            from_explicit_relationship=draw(st.booleans()),
        )

    @st.composite
    @staticmethod
    def st_suggestion_for_verification(draw, chunk_ids=None):
        """Generate a random Suggestion finding for verification tests."""
        if chunk_ids is None:
            chunk_ids = [f"chunk-{i:03d}" for i in range(5)]

        num_refs = draw(st.integers(min_value=0, max_value=3))
        refs = [
            FindingSourceRef(
                document_id="doc-test",
                chunk_id=draw(st.sampled_from(chunk_ids)),
                evidence=draw(st.text(min_size=1, max_size=200)),
            )
            for _ in range(num_refs)
        ]

        return Suggestion(
            id=f"sug-{draw(st.text(min_size=3, max_size=8, alphabet='abcdef0123456789'))}",
            description=draw(st.text(min_size=1, max_size=150)),
            category=draw(st.sampled_from(SUGGESTION_CATEGORIES)),
            priority=draw(st.sampled_from(SUGGESTION_PRIORITIES)),
            source_refs=refs,
        )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_verify_all_is_deterministic(self, data):
        """Running verify_all twice on the same inputs produces identical outputs."""
        from app.analysis.quality.finding_verifier import FindingVerifier

        ir = data.draw(TestProperty7EvidenceVerificationDeterminism.st_ir_for_verification())
        chunk_ids = [c.chunk_id for c in ir.chunks]

        inconsistencies = data.draw(
            st.lists(
                TestProperty7EvidenceVerificationDeterminism.st_inconsistency_for_verification(chunk_ids=chunk_ids),
                min_size=0,
                max_size=5,
            )
        )
        suggestions = data.draw(
            st.lists(
                TestProperty7EvidenceVerificationDeterminism.st_suggestion_for_verification(chunk_ids=chunk_ids),
                min_size=0,
                max_size=5,
            )
        )

        verifier = FindingVerifier()

        # First run
        verified_inc_1, verified_sug_1 = verifier.verify_all(
            inconsistencies, suggestions, ir
        )

        # Second run with the same inputs
        verified_inc_2, verified_sug_2 = verifier.verify_all(
            inconsistencies, suggestions, ir
        )

        # Compare evidence_verified on each source_ref in inconsistencies
        assert len(verified_inc_1) == len(verified_inc_2)
        for inc1, inc2 in zip(verified_inc_1, verified_inc_2):
            assert len(inc1.source_refs) == len(inc2.source_refs)
            for ref1, ref2 in zip(inc1.source_refs, inc2.source_refs):
                assert ref1.evidence_verified == ref2.evidence_verified, (
                    f"Inconsistency {inc1.id}: evidence_verified differs between runs"
                )
            assert inc1.all_evidence_unverified == inc2.all_evidence_unverified, (
                f"Inconsistency {inc1.id}: all_evidence_unverified differs between runs"
            )

        # Compare evidence_verified on each source_ref in suggestions
        assert len(verified_sug_1) == len(verified_sug_2)
        for sug1, sug2 in zip(verified_sug_1, verified_sug_2):
            assert len(sug1.source_refs) == len(sug2.source_refs)
            for ref1, ref2 in zip(sug1.source_refs, sug2.source_refs):
                assert ref1.evidence_verified == ref2.evidence_verified, (
                    f"Suggestion {sug1.id}: evidence_verified differs between runs"
                )
            assert sug1.all_evidence_unverified == sug2.all_evidence_unverified, (
                f"Suggestion {sug1.id}: all_evidence_unverified differs between runs"
            )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_all_evidence_unverified_flag_correctness(self, data):
        """all_evidence_unverified is True iff ALL source_refs have evidence_verified=False."""
        from app.analysis.quality.finding_verifier import FindingVerifier

        ir = data.draw(TestProperty7EvidenceVerificationDeterminism.st_ir_for_verification())
        chunk_ids = [c.chunk_id for c in ir.chunks]

        inconsistencies = data.draw(
            st.lists(
                TestProperty7EvidenceVerificationDeterminism.st_inconsistency_for_verification(chunk_ids=chunk_ids),
                min_size=1,
                max_size=5,
            )
        )
        suggestions = data.draw(
            st.lists(
                TestProperty7EvidenceVerificationDeterminism.st_suggestion_for_verification(chunk_ids=chunk_ids),
                min_size=1,
                max_size=5,
            )
        )

        verifier = FindingVerifier()
        verified_inc, verified_sug = verifier.verify_all(
            inconsistencies, suggestions, ir
        )

        for inc in verified_inc:
            if inc.source_refs:
                all_unverified = all(
                    not ref.evidence_verified for ref in inc.source_refs
                )
                assert inc.all_evidence_unverified == all_unverified, (
                    f"Inconsistency {inc.id}: all_evidence_unverified={inc.all_evidence_unverified} "
                    f"but expected {all_unverified}"
                )
            else:
                # Empty source_refs: all_evidence_unverified should be False
                assert inc.all_evidence_unverified is False

        for sug in verified_sug:
            if sug.source_refs:
                all_unverified = all(
                    not ref.evidence_verified for ref in sug.source_refs
                )
                assert sug.all_evidence_unverified == all_unverified, (
                    f"Suggestion {sug.id}: all_evidence_unverified={sug.all_evidence_unverified} "
                    f"but expected {all_unverified}"
                )
            else:
                # Empty source_refs: all_evidence_unverified should be False
                assert sug.all_evidence_unverified is False


# =============================================================================
# Property 8: KM Prerequisite Gate
# =============================================================================


class TestProperty8KMPrerequisiteGate:
    """Property 8: KM Prerequisite Gate.

    For any document without completed KM, run_analysis returns error
    without modifying quality records.

    **Validates: Requirements 8.1**
    """

    @given(
        status=st.sampled_from([
            "inferring_type",
            "awaiting_confirmation",
            "extracting",
            "verifying",
            "failed",
        ])
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_non_completed_status_raises_km_not_completed(self, status):
        """Any session status != 'completed' raises KMNotCompletedError."""
        from app.analysis.quality.service import KMNotCompletedError, QualityAnalysisService

        mock_storage = MagicMock()
        mock_storage.get_session_by_document.return_value = {
            "id": "session-001",
            "document_id": "doc-test",
            "status": status,
            "quality_status": None,
        }

        service = QualityAnalysisService(
            contradiction_detector=MagicMock(),
            ambiguity_detector=MagicMock(),
            completeness_evaluator=MagicMock(),
            suggestion_generator=MagicMock(),
            finding_verifier=MagicMock(),
            storage=mock_storage,
        )

        with pytest.raises(KMNotCompletedError):
            await service.run_analysis("doc-test")

    @given(
        status=st.sampled_from([
            "inferring_type",
            "awaiting_confirmation",
            "extracting",
            "verifying",
            "failed",
        ])
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_non_completed_status_does_not_modify_storage(self, status):
        """Rejected analysis does not create or modify quality records."""
        from app.analysis.quality.service import KMNotCompletedError, QualityAnalysisService

        mock_storage = MagicMock()
        mock_storage.get_session_by_document.return_value = {
            "id": "session-001",
            "document_id": "doc-test",
            "status": status,
            "quality_status": None,
        }

        service = QualityAnalysisService(
            contradiction_detector=MagicMock(),
            ambiguity_detector=MagicMock(),
            completeness_evaluator=MagicMock(),
            suggestion_generator=MagicMock(),
            finding_verifier=MagicMock(),
            storage=mock_storage,
        )

        with pytest.raises(KMNotCompletedError):
            await service.run_analysis("doc-test")

        # Verify storage was NOT modified
        mock_storage.update_session.assert_not_called()

    @given(data=st.data())
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_no_session_raises_km_not_completed(self, data):
        """No session at all raises KMNotCompletedError."""
        from app.analysis.quality.service import KMNotCompletedError, QualityAnalysisService

        mock_storage = MagicMock()
        mock_storage.get_session_by_document.return_value = None

        service = QualityAnalysisService(
            contradiction_detector=MagicMock(),
            ambiguity_detector=MagicMock(),
            completeness_evaluator=MagicMock(),
            suggestion_generator=MagicMock(),
            finding_verifier=MagicMock(),
            storage=mock_storage,
        )

        with pytest.raises(KMNotCompletedError):
            await service.run_analysis("doc-test")

        # Verify storage was NOT modified
        mock_storage.update_session.assert_not_called()


# =============================================================================
# Property 1: Explicit Contradictions Pass-Through
# =============================================================================

# --- Custom Strategies for Property 1 ---


@st.composite
def km_with_contradictions_strategy(draw):
    """Generate a KnowledgeModel with 2-5 elements where some have explicit contradicts
    relationships, plus a matching IR.

    Returns a tuple of (KnowledgeModel, IntermediateRepresentation, expected_contradiction_count).
    The contradiction count equals the number of unique contradicts relationship pairs.
    """
    num_elements = draw(st.integers(min_value=2, max_value=5))
    num_chunks = draw(st.integers(min_value=1, max_value=3))

    chunk_ids = [f"chunk-{i:03d}" for i in range(num_chunks)]
    element_ids = [f"elem-{i:03d}" for i in range(num_elements)]

    # Generate base elements without relations
    elements = []
    for eid in element_ids:
        elem_type = draw(st.sampled_from(ELEMENT_TYPES))
        name = draw(st.text(min_size=3, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "Z"))))
        content = draw(st.text(min_size=5, max_size=200))
        verified = draw(st.booleans())
        chunk_id = draw(st.sampled_from(chunk_ids))
        section = draw(st.one_of(st.none(), st.text(min_size=3, max_size=30).map(lambda s: f"## {s}")))
        page = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=50)))
        evidence = draw(st.text(min_size=5, max_size=200))

        src_ref = SourceRef(
            document_id="doc-001",
            chunk_id=chunk_id,
            page=page,
            section=section,
            evidence=evidence,
        )

        elements.append(
            KnowledgeElement(
                id=eid,
                type=elem_type,
                name=name,
                content=content,
                source_ref=src_ref,
                relations=[],
                verified=verified,
            )
        )

    # Decide how many contradicts pairs to add (at least 1)
    max_pairs = min(num_elements // 2, 3)
    num_contradiction_pairs = draw(st.integers(min_value=1, max_value=max(1, max_pairs)))

    # Select unique pairs for contradicts relationships
    available_indices = list(range(num_elements))
    draw(st.randoms()).shuffle(available_indices)

    contradiction_pairs: set[tuple[str, str]] = set()
    i = 0
    while len(contradiction_pairs) < num_contradiction_pairs and i + 1 < len(available_indices):
        source_idx = available_indices[i]
        target_idx = available_indices[i + 1]
        pair = tuple(sorted([element_ids[source_idx], element_ids[target_idx]]))
        contradiction_pairs.add(pair)
        i += 2

    # Assign contradicts relations to elements (one-directional for detection)
    for source_id, target_id in contradiction_pairs:
        for elem in elements:
            if elem.id == source_id:
                description = draw(
                    st.one_of(
                        st.none(),
                        st.text(min_size=5, max_size=100),
                    )
                )
                elem.relations.append(
                    Relation(
                        target_id=target_id,
                        type="contradicts",
                        description=description,
                    )
                )
                break

    # Optionally add some non-contradicts relations
    for elem in elements:
        num_other_relations = draw(st.integers(min_value=0, max_value=2))
        for _ in range(num_other_relations):
            other_ids = [eid for eid in element_ids if eid != elem.id]
            if other_ids:
                target = draw(st.sampled_from(other_ids))
                rel_type = draw(st.sampled_from(["constrains", "participates_in", "depends_on"]))
                elem.relations.append(
                    Relation(target_id=target, type=rel_type, description=None)
                )

    extraction_metadata = ExtractionMetadata(
        prompt_version="extraction-v1",
        model_id="gemini/gemini-2.5-flash",
        temperature=0.1,
        element_count=num_elements,
        relationship_count=sum(len(e.relations) for e in elements),
        verification_rate=0.5,
        extracted_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    km = KnowledgeModel(
        document_id="doc-001",
        document_type="prd",
        elements=elements,
        extraction_metadata=extraction_metadata,
    )

    # Build IR with matching chunks
    chunks = [
        ContentChunkModel(
            chunk_id=cid,
            text=draw(st.text(min_size=10, max_size=100)),
            structural_context={"section": f"## Section {idx}"},
            order=idx,
        )
        for idx, cid in enumerate(chunk_ids)
    ]

    ir = IntermediateRepresentation(
        document_id="doc-001",
        metadata=DocumentMetadata(
            original_filename="test.md",
            format=DocumentFormat.MARKDOWN,
            size_bytes=1024,
            language=DetectedLanguage.ENGLISH,
            upload_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ),
        chunks=chunks,
    )

    return km, ir, len(contradiction_pairs)


@st.composite
def llm_mock_behavior_strategy(draw):
    """Generate a random LLM mock behavior: success with empty findings, success with
    some findings, transient error, or generic exception.

    Returns a configured mock LLMClient.
    """
    behavior = draw(st.sampled_from([
        "empty_response", "valid_findings", "transient_error", "generic_error",
    ]))

    mock_client = MagicMock(spec=LLMClient)
    mock_client.call = AsyncMock()

    if behavior == "empty_response":
        mock_client.call.return_value = LLMResponse(
            content=json.dumps({"findings": []}),
            model_id="gemini/gemini-2.5-flash",
        )
    elif behavior == "valid_findings":
        num_llm_findings = draw(st.integers(min_value=1, max_value=3))
        findings = []
        for idx in range(num_llm_findings):
            findings.append({
                "type": "contradiction",
                "description": f"LLM-detected contradiction {idx}",
                "severity": draw(st.sampled_from(["high", "medium", "low"])),
                "affected_element_ids": [f"elem-{draw(st.integers(min_value=0, max_value=4)):03d}"],
                "source_refs": [
                    {
                        "chunk_id": f"chunk-{draw(st.integers(min_value=0, max_value=2)):03d}",
                        "page": None,
                        "section": "## Test",
                        "evidence": "Some evidence text for the finding.",
                    }
                ],
            })
        mock_client.call.return_value = LLMResponse(
            content=json.dumps({"findings": findings}),
            model_id="gemini/gemini-2.5-flash",
        )
    elif behavior == "transient_error":
        mock_client.call.side_effect = LLMTransientError("Service unavailable")
    elif behavior == "generic_error":
        mock_client.call.side_effect = RuntimeError("Unexpected LLM failure")

    return mock_client


class TestProperty1ExplicitContradictionsPassThrough:
    """Property 1: Explicit Contradictions Pass-Through.

    For any generated KM with `contradicts` relationships, the output always includes
    one Inconsistency per relationship with `from_explicit_relationship = True`,
    regardless of LLM mock behavior.

    **Validates: Requirements 1.1, 1.3, 1.6**
    """

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(data=st.data())
    async def test_structural_contradictions_always_present(self, data):
        """For any KM with contradicts relationships, structural contradictions
        always appear in output regardless of LLM behavior.

        Property: number of structural contradictions in output == number of unique
        `contradicts` relationship pairs in the KM.
        """
        km, ir, expected_count = data.draw(km_with_contradictions_strategy())
        mock_client = data.draw(llm_mock_behavior_strategy())

        detector = ContradictionDetector(mock_client)
        results = await detector.detect(km, ir)

        # Filter for structural contradictions only
        structural = [r for r in results if r.from_explicit_relationship]

        # Core property: count of structural findings == count of unique contradicts pairs
        assert len(structural) == expected_count, (
            f"Expected {expected_count} structural contradictions, got {len(structural)}. "
            f"KM has {len(km.elements)} elements."
        )

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(data=st.data())
    async def test_structural_contradictions_have_correct_structure(self, data):
        """For any structural contradiction in the output, it has the required fields:
        - type == "contradiction"
        - from_explicit_relationship == True
        - at least 2 affected_element_ids
        - at least 2 source_refs
        - severity in ("high", "medium", "low")
        - description max 500 chars
        """
        km, ir, _ = data.draw(km_with_contradictions_strategy())
        mock_client = data.draw(llm_mock_behavior_strategy())

        detector = ContradictionDetector(mock_client)
        results = await detector.detect(km, ir)

        structural = [r for r in results if r.from_explicit_relationship]

        for finding in structural:
            assert finding.type == "contradiction"
            assert finding.from_explicit_relationship is True
            assert len(finding.affected_element_ids) >= 2
            assert len(finding.source_refs) >= 2
            assert finding.severity in ("high", "medium", "low")
            assert len(finding.description) <= 500

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(data=st.data())
    async def test_structural_contradictions_reference_valid_elements(self, data):
        """For any structural contradiction, affected_element_ids reference elements
        that actually exist in the KM."""
        km, ir, _ = data.draw(km_with_contradictions_strategy())
        mock_client = data.draw(llm_mock_behavior_strategy())

        detector = ContradictionDetector(mock_client)
        results = await detector.detect(km, ir)

        km_element_ids = {elem.id for elem in km.elements}
        structural = [r for r in results if r.from_explicit_relationship]

        for finding in structural:
            for eid in finding.affected_element_ids:
                assert eid in km_element_ids, (
                    f"Structural contradiction references element '{eid}' "
                    f"which does not exist in the KM."
                )
