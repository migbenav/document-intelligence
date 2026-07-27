"""Unit tests for On-Demand Analysis Pydantic models.

Validates model construction, serialization, and constraint enforcement
for the on-demand analysis data models.

Requirements: Req 2 (criterion 2), Req 9 (criterion 1)
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.analysis.on_demand.models import (
    AnalysisRecord,
    AnalysisStatus,
    AnalysisType,
    AnsweredQuestion,
    ConclusionsResult,
    IndexResult,
    Observation,
    QuestionsResult,
    RelationsResult,
    SectionRelation,
    SourceRef,
    StructureNode,
)


# --- SourceRef Tests ---


class TestSourceRef:
    def test_text_excerpt_accepts_exactly_500_chars(self):
        """SourceRef allows text_excerpt of exactly 500 characters."""
        text = "a" * 500
        ref = SourceRef(chunk_ids=["c1"], text_excerpt=text)
        assert len(ref.text_excerpt) == 500

    def test_text_excerpt_truncates_over_500_chars(self):
        """SourceRef truncates text_excerpt longer than 500 characters."""
        text = "a" * 600
        ref = SourceRef(chunk_ids=["c1"], text_excerpt=text)
        assert len(ref.text_excerpt) == 500
        assert ref.text_excerpt.endswith("...")

    def test_section_is_optional(self):
        """SourceRef allows section to be None."""
        ref = SourceRef(chunk_ids=["c1", "c2"], text_excerpt="some text")
        assert ref.section is None

    def test_section_can_be_set(self):
        """SourceRef accepts a section string."""
        ref = SourceRef(chunk_ids=["c1"], text_excerpt="text", section="Chapter 1")
        assert ref.section == "Chapter 1"


# --- StructureNode Tests ---


class TestStructureNode:
    def test_recursive_children_serialization(self):
        """StructureNode with nested children serializes and deserializes correctly."""
        grandchild = StructureNode(
            id="n3",
            title="Subsection 1.1.1",
            level=3,
            role="describes",
            children=[],
        )
        child = StructureNode(
            id="n2",
            title="Section 1.1",
            level=2,
            role="defines",
            children=[grandchild],
        )
        root = StructureNode(
            id="n1",
            title="Chapter 1",
            level=1,
            role="establishes",
            question_answered="What is the purpose?",
            children=[child],
        )

        # Serialize to dict
        data = root.model_dump()
        assert data["id"] == "n1"
        assert data["children"][0]["id"] == "n2"
        assert data["children"][0]["children"][0]["id"] == "n3"

        # Round-trip: deserialize back
        restored = StructureNode.model_validate(data)
        assert restored.id == "n1"
        assert restored.children[0].id == "n2"
        assert restored.children[0].children[0].id == "n3"
        assert restored.children[0].children[0].title == "Subsection 1.1.1"

    def test_level_boundary_1_succeeds(self):
        """StructureNode accepts level=1 (minimum valid)."""
        node = StructureNode(id="n1", title="Root", level=1)
        assert node.level == 1

    def test_level_boundary_6_succeeds(self):
        """StructureNode accepts level=6 (maximum valid)."""
        node = StructureNode(id="n1", title="Deep", level=6)
        assert node.level == 6

    def test_level_0_fails(self):
        """StructureNode rejects level=0 (below minimum)."""
        with pytest.raises(ValidationError) as exc_info:
            StructureNode(id="n1", title="Bad", level=0)
        assert "level" in str(exc_info.value)

    def test_level_7_fails(self):
        """StructureNode rejects level=7 (above maximum)."""
        with pytest.raises(ValidationError) as exc_info:
            StructureNode(id="n1", title="Bad", level=7)
        assert "level" in str(exc_info.value)

    def test_empty_children_default(self):
        """StructureNode defaults children to empty list."""
        node = StructureNode(id="n1", title="Leaf", level=2)
        assert node.children == []


# --- SectionRelation Tests ---


class TestSectionRelation:
    @pytest.mark.parametrize(
        "relation_type",
        ["constrains", "depends_on", "complements", "contradicts"],
    )
    def test_valid_relation_types(self, relation_type):
        """SectionRelation accepts all four valid relation types."""
        rel = SectionRelation(
            source_section="Section A",
            target_section="Section B",
            type=relation_type,
            description="A relationship",
        )
        assert rel.type == relation_type

    def test_invalid_relation_type_raises(self):
        """SectionRelation rejects invalid type values."""
        with pytest.raises(ValidationError) as exc_info:
            SectionRelation(
                source_section="Section A",
                target_section="Section B",
                type="extends",
                description="Invalid type",
            )
        assert "type" in str(exc_info.value)


# --- AnsweredQuestion Tests ---


class TestAnsweredQuestion:
    def test_level_document_valid(self):
        """AnsweredQuestion accepts level='document'."""
        q = AnsweredQuestion(
            question="What is the document about?",
            level="document",
        )
        assert q.level == "document"

    def test_level_section_valid(self):
        """AnsweredQuestion accepts level='section'."""
        q = AnsweredQuestion(
            question="What does Chapter 1 cover?",
            level="section",
            section_title="Chapter 1",
        )
        assert q.level == "section"

    def test_invalid_level_raises(self):
        """AnsweredQuestion rejects invalid level values."""
        with pytest.raises(ValidationError) as exc_info:
            AnsweredQuestion(
                question="A question",
                level="paragraph",
            )
        assert "level" in str(exc_info.value)


# --- Observation Tests ---


class TestObservation:
    @pytest.mark.parametrize(
        "category",
        ["coherence", "reordering", "duplication", "orphan", "missing"],
    )
    def test_valid_categories(self, category):
        """Observation accepts all 5 valid category values."""
        obs = Observation(
            category=category,
            description="An observation",
            suggestion="Move section X before section Y",
        )
        assert obs.category == category

    def test_invalid_category_raises(self):
        """Observation rejects invalid category values."""
        with pytest.raises(ValidationError) as exc_info:
            Observation(
                category="style",
                description="Not valid",
                suggestion="Fix it",
            )
        assert "category" in str(exc_info.value)


# --- AnalysisRecord JSON Round-Trip Tests ---


class TestAnalysisRecordRoundTrip:
    def _make_record(self, analysis_type: AnalysisType, result: dict) -> AnalysisRecord:
        """Helper to build an AnalysisRecord with the given type and result."""
        return AnalysisRecord(
            id="rec-001",
            document_id="doc-001",
            analysis_type=analysis_type,
            status=AnalysisStatus.COMPLETED,
            result=result,
            model_id="gemini/gemini-2.5-flash",
            prompt_version="test-v1",
            error_message=None,
            created_at=datetime(2026, 7, 26, 15, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 26, 15, 0, 12, tzinfo=timezone.utc),
        )

    def test_round_trip_with_index_result(self):
        """AnalysisRecord serializes and deserializes with IndexResult dict."""
        index_data = IndexResult(
            tree=[
                StructureNode(
                    id="n1",
                    title="Introduction",
                    level=1,
                    role="describes",
                    question_answered="What is this document?",
                    source_ref=SourceRef(
                        chunk_ids=["c1", "c2"],
                        text_excerpt="This document describes...",
                        section="Introduction",
                    ),
                    children=[
                        StructureNode(
                            id="n2",
                            title="Background",
                            level=2,
                            children=[],
                        )
                    ],
                )
            ]
        )
        record = self._make_record(
            AnalysisType.BUILD_INDEX, index_data.model_dump()
        )

        # Serialize to JSON and back
        json_str = record.model_dump_json()
        restored = AnalysisRecord.model_validate_json(json_str)

        assert restored.id == "rec-001"
        assert restored.analysis_type == AnalysisType.BUILD_INDEX
        assert restored.result["tree"][0]["id"] == "n1"
        assert restored.result["tree"][0]["children"][0]["id"] == "n2"

    def test_round_trip_with_relations_result(self):
        """AnalysisRecord serializes and deserializes with RelationsResult dict."""
        relations_data = RelationsResult(
            relations=[
                SectionRelation(
                    source_section="Chapter 1",
                    target_section="Chapter 3",
                    type="depends_on",
                    description="Chapter 3 uses definitions from Chapter 1",
                    source_ref=SourceRef(
                        chunk_ids=["c5"],
                        text_excerpt="As defined in Chapter 1...",
                    ),
                ),
                SectionRelation(
                    source_section="Section 2.1",
                    target_section="Section 2.3",
                    type="contradicts",
                    description="These sections state conflicting requirements",
                ),
            ]
        )
        record = self._make_record(
            AnalysisType.SECTION_RELATIONS, relations_data.model_dump()
        )

        json_str = record.model_dump_json()
        restored = AnalysisRecord.model_validate_json(json_str)

        assert restored.analysis_type == AnalysisType.SECTION_RELATIONS
        assert len(restored.result["relations"]) == 2
        assert restored.result["relations"][0]["type"] == "depends_on"
        assert restored.result["relations"][1]["type"] == "contradicts"


# --- Enum Value Tests ---


class TestEnumValues:
    def test_analysis_type_has_exactly_4_values(self):
        """AnalysisType enum has exactly the 4 values from the design spec."""
        expected = {"build_index", "section_relations", "questions_answered", "conclusions"}
        actual = {member.value for member in AnalysisType}
        assert actual == expected
        assert len(AnalysisType) == 4

    def test_analysis_status_has_exactly_5_values(self):
        """AnalysisStatus enum has exactly the 5 values from the design spec."""
        expected = {"not_started", "in_progress", "completed", "outdated", "failed"}
        actual = {member.value for member in AnalysisStatus}
        assert actual == expected
        assert len(AnalysisStatus) == 5
