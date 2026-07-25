"""Unit tests for the Quality Analysis Pydantic models.

Verifies serialization, validation, and field constraints (max lengths, literal values)
for all models defined in app.models.quality_analysis.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.quality_analysis import (
    FindingSourceRef,
    Inconsistency,
    MissingElement,
    QualityAnalysisMetadata,
    QualityAnalysisResult,
    Suggestion,
)


# --- Fixtures ---


@pytest.fixture
def sample_source_ref() -> FindingSourceRef:
    return FindingSourceRef(
        document_id="doc-001",
        chunk_id="chunk-003",
        page=5,
        section="## Performance Requirements",
        evidence="All API endpoints must respond within 200ms",
        evidence_verified=True,
    )


@pytest.fixture
def sample_source_ref_unverified() -> FindingSourceRef:
    return FindingSourceRef(
        document_id="doc-001",
        chunk_id="chunk-008",
        section="## SLA Definitions",
        evidence="Response time SLA: 500ms for standard endpoints",
        evidence_verified=False,
    )


@pytest.fixture
def sample_inconsistency(
    sample_source_ref: FindingSourceRef,
    sample_source_ref_unverified: FindingSourceRef,
) -> Inconsistency:
    return Inconsistency(
        id="inc-001",
        type="contradiction",
        description="Section 3.1 states max response time is 200ms, while Section 5.2 requires responses within 500ms for the same endpoint.",
        severity="high",
        affected_element_ids=["elem-005", "elem-012"],
        source_refs=[sample_source_ref, sample_source_ref_unverified],
        involves_unverified_elements=False,
        all_evidence_unverified=False,
        from_explicit_relationship=True,
    )


@pytest.fixture
def sample_missing_element() -> MissingElement:
    return MissingElement(
        id="miss-001",
        classification="missing",
        expected_element="criterios de éxito",
        description="PRD documents should define measurable success criteria.",
        severity="medium",
        schema_reference="prd",
    )


@pytest.fixture
def sample_suggestion(sample_source_ref: FindingSourceRef) -> Suggestion:
    return Suggestion(
        id="sug-001",
        description="Add a section defining measurable success criteria with specific KPIs and target values.",
        category="completeness",
        priority="medium",
        related_finding_ids=["miss-001"],
        source_refs=[sample_source_ref],
        all_evidence_unverified=False,
    )


@pytest.fixture
def sample_metadata() -> QualityAnalysisMetadata:
    return QualityAnalysisMetadata(
        prompt_versions={
            "contradiction_detection": "contradiction-v1",
            "ambiguity_detection": "ambiguity-v1",
            "completeness_evaluation": "completeness-v1",
            "suggestion_generation": "suggestion-v1",
        },
        model_id="gemini/gemini-2.5-flash-preview-05-20",
        temperature=0.1,
        document_type="prd",
        started_at=datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 7, 28, 10, 1, 15, tzinfo=timezone.utc),
        finding_counts={
            "contradictions": 2,
            "ambiguities": 3,
            "missing_elements": 1,
            "suggestions": 5,
        },
    )


# --- FindingSourceRef Tests ---


class TestFindingSourceRef:
    def test_serialization_with_all_fields(self, sample_source_ref: FindingSourceRef):
        data = sample_source_ref.model_dump()
        assert data["document_id"] == "doc-001"
        assert data["chunk_id"] == "chunk-003"
        assert data["page"] == 5
        assert data["section"] == "## Performance Requirements"
        assert data["evidence"] == "All API endpoints must respond within 200ms"
        assert data["evidence_verified"] is True

    def test_page_and_section_optional(self):
        ref = FindingSourceRef(
            document_id="doc-001",
            chunk_id="chunk-001",
            evidence="Some evidence text",
        )
        assert ref.page is None
        assert ref.section is None

    def test_evidence_verified_defaults_false(self):
        ref = FindingSourceRef(
            document_id="doc-001",
            chunk_id="chunk-001",
            evidence="Some text",
        )
        assert ref.evidence_verified is False

    def test_evidence_max_length_500(self):
        """Evidence text span is limited to 500 characters (Req 7.3)."""
        # Exactly 500 should work
        ref = FindingSourceRef(
            document_id="doc-001",
            chunk_id="chunk-001",
            evidence="x" * 500,
        )
        assert len(ref.evidence) == 500

        # 501 should fail
        with pytest.raises(ValidationError) as exc_info:
            FindingSourceRef(
                document_id="doc-001",
                chunk_id="chunk-001",
                evidence="x" * 501,
            )
        assert "evidence" in str(exc_info.value).lower()

    def test_evidence_required(self):
        with pytest.raises(ValidationError):
            FindingSourceRef(
                document_id="doc-001",
                chunk_id="chunk-001",
            )

    def test_json_round_trip(self, sample_source_ref: FindingSourceRef):
        json_str = sample_source_ref.model_dump_json()
        restored = FindingSourceRef.model_validate_json(json_str)
        assert restored == sample_source_ref


# --- Inconsistency Tests ---


class TestInconsistency:
    def test_valid_types(self, sample_source_ref: FindingSourceRef):
        for inc_type in ["contradiction", "ambiguity"]:
            inc = Inconsistency(
                id="inc-001",
                type=inc_type,
                description="Some inconsistency",
                severity="medium",
                affected_element_ids=["elem-001"],
                source_refs=[sample_source_ref],
            )
            assert inc.type == inc_type

    def test_invalid_type_rejected(self, sample_source_ref: FindingSourceRef):
        with pytest.raises(ValidationError):
            Inconsistency(
                id="inc-001",
                type="typo",
                description="Not a valid type",
                severity="medium",
                affected_element_ids=["elem-001"],
                source_refs=[sample_source_ref],
            )

    def test_valid_severity_levels(self, sample_source_ref: FindingSourceRef):
        for severity in ["high", "medium", "low"]:
            inc = Inconsistency(
                id="inc-001",
                type="ambiguity",
                description="Ambiguous statement",
                severity=severity,
                affected_element_ids=["elem-001"],
                source_refs=[sample_source_ref],
            )
            assert inc.severity == severity

    def test_invalid_severity_rejected(self, sample_source_ref: FindingSourceRef):
        with pytest.raises(ValidationError):
            Inconsistency(
                id="inc-001",
                type="contradiction",
                description="Test",
                severity="critical",
                affected_element_ids=["elem-001"],
                source_refs=[sample_source_ref],
            )

    def test_description_max_length_500(self, sample_source_ref: FindingSourceRef):
        """Description is limited to 500 characters (Req 1.2)."""
        # Exactly 500 should work
        inc = Inconsistency(
            id="inc-001",
            type="contradiction",
            description="d" * 500,
            severity="high",
            affected_element_ids=["elem-001", "elem-002"],
            source_refs=[sample_source_ref],
        )
        assert len(inc.description) == 500

        # 501 should fail
        with pytest.raises(ValidationError) as exc_info:
            Inconsistency(
                id="inc-001",
                type="contradiction",
                description="d" * 501,
                severity="high",
                affected_element_ids=["elem-001"],
                source_refs=[sample_source_ref],
            )
        assert "description" in str(exc_info.value).lower()

    def test_boolean_defaults(self, sample_source_ref: FindingSourceRef):
        inc = Inconsistency(
            id="inc-001",
            type="ambiguity",
            description="Vague quantifier found",
            severity="low",
            affected_element_ids=["elem-001"],
            source_refs=[sample_source_ref],
        )
        assert inc.involves_unverified_elements is False
        assert inc.all_evidence_unverified is False
        assert inc.from_explicit_relationship is False

    def test_full_serialization(self, sample_inconsistency: Inconsistency):
        data = sample_inconsistency.model_dump()
        assert data["id"] == "inc-001"
        assert data["type"] == "contradiction"
        assert data["severity"] == "high"
        assert len(data["affected_element_ids"]) == 2
        assert len(data["source_refs"]) == 2
        assert data["from_explicit_relationship"] is True

    def test_json_round_trip(self, sample_inconsistency: Inconsistency):
        json_str = sample_inconsistency.model_dump_json()
        restored = Inconsistency.model_validate_json(json_str)
        assert restored == sample_inconsistency


# --- MissingElement Tests ---


class TestMissingElement:
    def test_valid_classifications(self):
        for classification in ["missing", "partial"]:
            elem = MissingElement(
                id="miss-001",
                classification=classification,
                expected_element="propósito",
                description="Element is expected",
                severity="high",
                schema_reference="prd",
            )
            assert elem.classification == classification

    def test_invalid_classification_rejected(self):
        with pytest.raises(ValidationError):
            MissingElement(
                id="miss-001",
                classification="absent",
                expected_element="propósito",
                description="Invalid classification",
                severity="high",
                schema_reference="prd",
            )

    def test_valid_severity_levels(self):
        for severity in ["high", "medium", "low"]:
            elem = MissingElement(
                id="miss-001",
                classification="missing",
                expected_element="restricciones",
                description="Missing constraints section",
                severity=severity,
                schema_reference="technical_spec",
            )
            assert elem.severity == severity

    def test_invalid_severity_rejected(self):
        with pytest.raises(ValidationError):
            MissingElement(
                id="miss-001",
                classification="missing",
                expected_element="propósito",
                description="Test",
                severity="urgent",
                schema_reference="prd",
            )

    def test_full_serialization(self, sample_missing_element: MissingElement):
        data = sample_missing_element.model_dump()
        assert data["id"] == "miss-001"
        assert data["classification"] == "missing"
        assert data["expected_element"] == "criterios de éxito"
        assert data["severity"] == "medium"
        assert data["schema_reference"] == "prd"

    def test_json_round_trip(self, sample_missing_element: MissingElement):
        json_str = sample_missing_element.model_dump_json()
        restored = MissingElement.model_validate_json(json_str)
        assert restored == sample_missing_element


# --- Suggestion Tests ---


class TestSuggestion:
    def test_valid_categories(self, sample_source_ref: FindingSourceRef):
        for category in ["structure", "clarity", "completeness", "consistency"]:
            sug = Suggestion(
                id="sug-001",
                description="Improve something",
                category=category,
                priority="medium",
                source_refs=[sample_source_ref],
            )
            assert sug.category == category

    def test_invalid_category_rejected(self, sample_source_ref: FindingSourceRef):
        with pytest.raises(ValidationError):
            Suggestion(
                id="sug-001",
                description="Test",
                category="formatting",
                priority="medium",
                source_refs=[sample_source_ref],
            )

    def test_valid_priorities(self, sample_source_ref: FindingSourceRef):
        for priority in ["high", "medium", "low"]:
            sug = Suggestion(
                id="sug-001",
                description="Do something",
                category="structure",
                priority=priority,
                source_refs=[sample_source_ref],
            )
            assert sug.priority == priority

    def test_invalid_priority_rejected(self, sample_source_ref: FindingSourceRef):
        with pytest.raises(ValidationError):
            Suggestion(
                id="sug-001",
                description="Test",
                category="structure",
                priority="critical",
                source_refs=[sample_source_ref],
            )

    def test_description_max_length_300(self, sample_source_ref: FindingSourceRef):
        """Suggestion description is limited to 300 characters (Req 4.2)."""
        # Exactly 300 should work
        sug = Suggestion(
            id="sug-001",
            description="s" * 300,
            category="clarity",
            priority="low",
            source_refs=[sample_source_ref],
        )
        assert len(sug.description) == 300

        # 301 should fail
        with pytest.raises(ValidationError) as exc_info:
            Suggestion(
                id="sug-001",
                description="s" * 301,
                category="clarity",
                priority="low",
                source_refs=[sample_source_ref],
            )
        assert "description" in str(exc_info.value).lower()

    def test_defaults_empty_lists(self):
        sug = Suggestion(
            id="sug-001",
            description="A suggestion",
            category="structure",
            priority="medium",
        )
        assert sug.related_finding_ids == []
        assert sug.source_refs == []
        assert sug.all_evidence_unverified is False

    def test_full_serialization(self, sample_suggestion: Suggestion):
        data = sample_suggestion.model_dump()
        assert data["id"] == "sug-001"
        assert data["category"] == "completeness"
        assert data["priority"] == "medium"
        assert data["related_finding_ids"] == ["miss-001"]
        assert len(data["source_refs"]) == 1

    def test_json_round_trip(self, sample_suggestion: Suggestion):
        json_str = sample_suggestion.model_dump_json()
        restored = Suggestion.model_validate_json(json_str)
        assert restored == sample_suggestion


# --- QualityAnalysisMetadata Tests ---


class TestQualityAnalysisMetadata:
    def test_serialization(self, sample_metadata: QualityAnalysisMetadata):
        data = sample_metadata.model_dump()
        assert data["model_id"] == "gemini/gemini-2.5-flash-preview-05-20"
        assert data["temperature"] == 0.1
        assert data["document_type"] == "prd"
        assert data["prompt_versions"]["contradiction_detection"] == "contradiction-v1"
        assert data["finding_counts"]["contradictions"] == 2
        assert data["finding_counts"]["suggestions"] == 5

    def test_timestamps_serialization(self, sample_metadata: QualityAnalysisMetadata):
        data = sample_metadata.model_dump(mode="json")
        assert "2026-07-28" in data["started_at"]
        assert "2026-07-28" in data["completed_at"]

    def test_all_fields_required(self):
        with pytest.raises(ValidationError):
            QualityAnalysisMetadata(
                prompt_versions={},
                model_id="model",
                # missing temperature, document_type, timestamps, finding_counts
            )

    def test_json_round_trip(self, sample_metadata: QualityAnalysisMetadata):
        json_str = sample_metadata.model_dump_json()
        restored = QualityAnalysisMetadata.model_validate_json(json_str)
        assert restored == sample_metadata


# --- QualityAnalysisResult Tests ---


class TestQualityAnalysisResult:
    def test_valid_statuses(self):
        for status in ["analyzing", "completed", "failed"]:
            result = QualityAnalysisResult(
                document_id="doc-001",
                status=status,
            )
            assert result.status == status

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            QualityAnalysisResult(
                document_id="doc-001",
                status="pending",
            )

    def test_defaults_empty_lists_and_none(self):
        result = QualityAnalysisResult(
            document_id="doc-001",
            status="analyzing",
        )
        assert result.inconsistencies == []
        assert result.missing_elements == []
        assert result.suggestions == []
        assert result.metadata is None
        assert result.error_message is None
        assert result.error_phase is None

    def test_failed_result_with_error(self):
        result = QualityAnalysisResult(
            document_id="doc-001",
            status="failed",
            error_message="LLM service unavailable during ambiguity detection",
            error_phase="analyzing_ambiguities",
        )
        assert result.status == "failed"
        assert result.error_message == "LLM service unavailable during ambiguity detection"
        assert result.error_phase == "analyzing_ambiguities"

    def test_completed_result_with_all_findings(
        self,
        sample_inconsistency: Inconsistency,
        sample_missing_element: MissingElement,
        sample_suggestion: Suggestion,
        sample_metadata: QualityAnalysisMetadata,
    ):
        result = QualityAnalysisResult(
            document_id="doc-001",
            status="completed",
            inconsistencies=[sample_inconsistency],
            missing_elements=[sample_missing_element],
            suggestions=[sample_suggestion],
            metadata=sample_metadata,
        )
        data = result.model_dump()
        assert data["status"] == "completed"
        assert len(data["inconsistencies"]) == 1
        assert len(data["missing_elements"]) == 1
        assert len(data["suggestions"]) == 1
        assert data["metadata"]["model_id"] == "gemini/gemini-2.5-flash-preview-05-20"

    def test_json_round_trip(
        self,
        sample_inconsistency: Inconsistency,
        sample_missing_element: MissingElement,
        sample_suggestion: Suggestion,
        sample_metadata: QualityAnalysisMetadata,
    ):
        result = QualityAnalysisResult(
            document_id="doc-001",
            status="completed",
            inconsistencies=[sample_inconsistency],
            missing_elements=[sample_missing_element],
            suggestions=[sample_suggestion],
            metadata=sample_metadata,
        )
        json_str = result.model_dump_json()
        restored = QualityAnalysisResult.model_validate_json(json_str)
        assert restored == result

    def test_partial_results_on_failure(self, sample_source_ref: FindingSourceRef):
        """Failed analysis can include explicit-relationship contradictions (Req 1.6)."""
        explicit_contradiction = Inconsistency(
            id="inc-structural-001",
            type="contradiction",
            description="Structural contradiction from explicit relationship",
            severity="high",
            affected_element_ids=["elem-001", "elem-002"],
            source_refs=[sample_source_ref, sample_source_ref],
            from_explicit_relationship=True,
        )
        result = QualityAnalysisResult(
            document_id="doc-001",
            status="failed",
            inconsistencies=[explicit_contradiction],
            error_message="LLM service unavailable",
            error_phase="analyzing_ambiguities",
        )
        assert result.status == "failed"
        assert len(result.inconsistencies) == 1
        assert result.inconsistencies[0].from_explicit_relationship is True
